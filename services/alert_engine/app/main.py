from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Response, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from libs.alert_events import AlertEventRepository

from .cache import AlertContextCache
from .clients import MarketDataClient, MarketDataStreamClient, NotificationPublisher, ReportsClient
from .config import AlertEngineSettings
from .database import create_session_factory, get_session
from .engine import AlertEngine
from .evaluator import RuleEvaluator
from .event_recorder import AlertEventRecorder
from .models import AlertRule
from .repository import AlertRuleRepository
from .schemas import (
    AlertEvaluationResponse,
    AlertRuleCreate,
    AlertRuleRead,
    AlertRuleSummary,
    AlertRuleUpdate,
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

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        """Expose a minimal readiness check for orchestrators and dashboards."""

        return {"status": "ok"}

    def get_engine() -> AlertEngine:
        return app.state.alert_engine

    def get_session_dep() -> Session:
        yield from get_session(app.state.session_factory)

    def get_repository() -> AlertRuleRepository:
        return repository

    @app.get("/alerts", response_model=list[AlertRuleRead])
    async def list_alert_rules(
        session: Session = Depends(get_session_dep),
        repository: AlertRuleRepository = Depends(get_repository),
    ) -> list[AlertRuleRead]:
        rules = await repository.list_rules(session)
        return [AlertRuleRead.from_orm_rule(rule) for rule in rules]

    @app.post("/alerts", response_model=AlertRuleRead, status_code=status.HTTP_201_CREATED)
    async def create_alert_rule(
        payload: AlertRuleCreate,
        session: Session = Depends(get_session_dep),
        repository: AlertRuleRepository = Depends(get_repository),
    ) -> AlertRuleRead:
        try:
            expression = payload.expression()
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error

        rule = AlertRule(
            name=payload.title.strip(),
            detail=payload.detail.strip(),
            symbol=payload.rule.symbol.strip(),
            expression=expression,
            severity=payload.risk,
            acknowledged=payload.acknowledged,
            channels=payload.dump_channels(),
            conditions=payload.dump_rule(),
            throttle_seconds=payload.throttle_seconds,
        )
        created = await repository.add_rule(session, rule)
        return AlertRuleRead.from_orm_rule(created)

    @app.put("/alerts/{alert_id}", response_model=AlertRuleRead)
    async def update_alert_rule(
        alert_id: int,
        payload: AlertRuleUpdate,
        session: Session = Depends(get_session_dep),
        repository: AlertRuleRepository = Depends(get_repository),
    ) -> AlertRuleRead:
        rule = await repository.get_rule(session, alert_id)
        if rule is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerte introuvable.")
        try:
            values = payload.to_update_mapping()
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        if not values:
            return AlertRuleRead.from_orm_rule(rule)
        if "name" in values and isinstance(values["name"], str):
            values["name"] = values["name"].strip()
        if "detail" in values and isinstance(values["detail"], str):
            values["detail"] = values["detail"].strip()
        if "symbol" in values and isinstance(values["symbol"], str):
            values["symbol"] = values["symbol"].strip()
        updated = await repository.update_rule(session, rule, values)
        return AlertRuleRead.from_orm_rule(updated)

    @app.delete("/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_alert_rule(
        alert_id: int,
        session: Session = Depends(get_session_dep),
        repository: AlertRuleRepository = Depends(get_repository),
    ) -> Response:
        rule = await repository.get_rule(session, alert_id)
        if rule is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerte introuvable.")
        await repository.delete_rule(session, rule)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

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

    @app.get("/alerts/triggers", response_model=list[AlertRuleSummary])
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
