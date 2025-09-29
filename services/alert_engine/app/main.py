from __future__ import annotations

from fastapi import Depends, FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from libs.alert_events import AlertEventRepository

from .cache import AlertContextCache
from .clients import (
    MarketDataClient,
    MarketDataStreamClient,
    NotificationPublisher,
    ReportsClient,
)
from .config import AlertEngineSettings
from .database import create_session_factory, get_session
from .engine import AlertEngine
from .evaluator import RuleEvaluator
from .event_recorder import AlertEventRecorder
from .repository import AlertRuleRepository
from .schemas import (
    AlertEvaluationResponse,
    AlertRuleSummary,
    AlertTriggerRead,
    MarketEvent,
)
from .streaming import StreamProcessor


def create_app(
    settings: AlertEngineSettings | None = None,
    session_factory: sessionmaker[Session] | None = None,
    market_client: MarketDataClient | None = None,
    reports_client: ReportsClient | None = None,
    stream_client: MarketDataStreamClient | None = None,
    context_cache: AlertContextCache | None = None,
    stream_processor: StreamProcessor | None = None,
    publisher: NotificationPublisher | None = None,
    start_background_tasks: bool = True,
) -> FastAPI:
    settings = settings or AlertEngineSettings.from_env()
    session_factory = session_factory or create_session_factory(settings)
    market_client = market_client or MarketDataClient(settings.market_data_url)
    reports_client = reports_client or ReportsClient(settings.reports_url)
    context_cache = context_cache or AlertContextCache(
        market_client=market_client,
        reports_client=reports_client,
        market_ttl_seconds=settings.market_snapshot_ttl_seconds,
        event_ttl_seconds=settings.market_event_ttl_seconds,
        reports_ttl_seconds=settings.reports_ttl_seconds,
    )
    stream_client = stream_client or MarketDataStreamClient(settings.market_data_stream_url)
    publisher = publisher or NotificationPublisher(settings.notification_url)

    repository = AlertRuleRepository()
    evaluator = RuleEvaluator()
    events_engine = create_engine(settings.events_database_url, future=True)
    events_session_factory = sessionmaker(
        bind=events_engine, autocommit=False, autoflush=False, future=True
    )
    engine = AlertEngine(
        repository=repository,
        evaluator=evaluator,
        context_cache=context_cache,
        publisher=publisher,
        evaluation_interval=settings.evaluation_interval_seconds,
        event_recorder=AlertEventRecorder(
            repository=AlertEventRepository(),
            session_factory=events_session_factory,
        ),
    )
    stream_processor = stream_processor or StreamProcessor(
        stream_client=stream_client,
        engine=engine,
        session_factory=session_factory,
    )

    app = FastAPI(title="Alert Engine")
    app.state.session_factory = session_factory
    app.state.alert_engine = engine
    app.state.context_cache = context_cache
    app.state.stream_processor = stream_processor
    app.state.clients = [market_client, reports_client, stream_client, publisher]

    if start_background_tasks:
        @app.on_event("startup")
        async def _startup() -> None:  # pragma: no cover - FastAPI wiring
            await engine.start_periodic_evaluation(session_factory)
            if settings.stream_symbols:
                await stream_processor.start(list(settings.stream_symbols))

        @app.on_event("shutdown")
        async def _shutdown() -> None:  # pragma: no cover - FastAPI wiring
            await engine.stop()
            await stream_processor.stop()
            for client in app.state.clients:
                await client.aclose()

    def get_engine() -> AlertEngine:
        return app.state.alert_engine

    def get_session_dep() -> Session:
        yield from get_session(app.state.session_factory)

    def get_repository() -> AlertRuleRepository:
        return repository

    @app.post("/events", response_model=AlertEvaluationResponse)
    async def receive_event(
        event: MarketEvent,
        session: Session = Depends(get_session_dep),
        engine: AlertEngine = Depends(get_engine),
    ) -> AlertEvaluationResponse:
        triggers = await engine.handle_event(session, event)
        return AlertEvaluationResponse(
            triggered=bool(triggers),
            triggers=[AlertTriggerRead.model_validate(t) for t in triggers],
        )

    @app.get("/alerts", response_model=list[AlertRuleSummary])
    async def list_recent_alerts(
        limit: int = 20,
        session: Session = Depends(get_session_dep),
        repository: AlertRuleRepository = Depends(get_repository),
    ) -> list[AlertRuleSummary]:
        limit = max(1, min(limit, 100))
        triggers = await repository.list_recent_triggers(session, limit=limit)
        summaries: list[AlertRuleSummary] = []
        for trigger in triggers:
            if trigger.rule is None:
                continue
            summaries.append(
                AlertRuleSummary(
                    trigger_id=trigger.id,
                    rule_id=trigger.rule_id,
                    name=trigger.rule.name,
                    symbol=trigger.rule.symbol,
                    severity=trigger.rule.severity,
                    expression=trigger.rule.expression,
                    triggered_at=trigger.triggered_at,
                    context=trigger.context,
                )
            )
        return summaries

    return app


app = create_app()
