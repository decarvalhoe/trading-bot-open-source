from __future__ import annotations

from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session, sessionmaker

from .clients import MarketDataClient, NotificationPublisher, ReportsClient
from .config import AlertEngineSettings
from .database import create_session_factory, get_session
from .engine import AlertEngine
from .evaluator import RuleEvaluator
from .repository import AlertRuleRepository
from .schemas import AlertEvaluationResponse, AlertTriggerRead, MarketEvent


def create_app(
    settings: AlertEngineSettings | None = None,
    session_factory: sessionmaker[Session] | None = None,
    market_client: MarketDataClient | None = None,
    reports_client: ReportsClient | None = None,
    publisher: NotificationPublisher | None = None,
    start_background_tasks: bool = True,
) -> FastAPI:
    settings = settings or AlertEngineSettings.from_env()
    session_factory = session_factory or create_session_factory(settings)
    market_client = market_client or MarketDataClient(settings.market_data_url)
    reports_client = reports_client or ReportsClient(settings.reports_url)
    publisher = publisher or NotificationPublisher(settings.notification_url)

    repository = AlertRuleRepository()
    evaluator = RuleEvaluator()
    engine = AlertEngine(
        repository=repository,
        evaluator=evaluator,
        market_client=market_client,
        reports_client=reports_client,
        publisher=publisher,
        evaluation_interval=settings.evaluation_interval_seconds,
    )

    app = FastAPI(title="Alert Engine")
    app.state.session_factory = session_factory
    app.state.alert_engine = engine
    app.state.clients = [market_client, reports_client, publisher]

    if start_background_tasks:
        @app.on_event("startup")
        async def _startup() -> None:  # pragma: no cover - FastAPI wiring
            await engine.start_periodic_evaluation(session_factory)

        @app.on_event("shutdown")
        async def _shutdown() -> None:  # pragma: no cover - FastAPI wiring
            await engine.stop()
            for client in app.state.clients:
                await client.aclose()

    def get_engine() -> AlertEngine:
        return app.state.alert_engine

    def get_session_dep() -> Session:
        yield from get_session(app.state.session_factory)

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

    return app


app = create_app()
