from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
import sqlalchemy
from sqlalchemy.orm import Session, sessionmaker

from services.alert_engine.app.clients import MarketDataClient, NotificationPublisher, ReportsClient
from services.alert_engine.app.config import AlertEngineSettings
from services.alert_engine.app.database import Base
from services.alert_engine.app.engine import AlertEngine
from services.alert_engine.app.evaluator import RuleEvaluator
from services.alert_engine.app.main import create_app
from services.alert_engine.app.models import AlertRule
from services.alert_engine.app.repository import AlertRuleRepository


class FakeMarketDataClient(MarketDataClient):
    def __init__(self, context: dict[str, Any]) -> None:
        self._context = context

    async def fetch_context(self, symbol: str) -> dict[str, Any]:
        return {**self._context, "symbol": symbol}

    async def aclose(self) -> None:  # pragma: no cover - interface requirement
        return None


class FakeReportsClient(ReportsClient):
    def __init__(self, context: dict[str, Any]) -> None:
        self._context = context

    async def fetch_context(self, symbol: str) -> dict[str, Any]:
        return self._context

    async def aclose(self) -> None:  # pragma: no cover - interface requirement
        return None


class DummyPublisher(NotificationPublisher):
    def __init__(self) -> None:
        self.published_payloads: list[dict[str, Any]] = []

    async def publish(self, payload: dict[str, Any]) -> None:
        self.published_payloads.append(payload)

    async def aclose(self) -> None:  # pragma: no cover - interface requirement
        return None


@pytest.fixture()
def in_memory_session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=sqlalchemy.pool.StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    yield factory
    engine.dispose()


@pytest.fixture()
def app(in_memory_session_factory: sessionmaker[Session]) -> FastAPI:
    settings = AlertEngineSettings(evaluation_interval_seconds=0.1)
    market_client = FakeMarketDataClient({"moving_average": 100.0})
    reports_client = FakeReportsClient({"daily_volume": 5000})
    publisher = DummyPublisher()
    return create_app(
        settings=settings,
        session_factory=in_memory_session_factory,
        market_client=market_client,
        reports_client=reports_client,
        publisher=publisher,
        start_background_tasks=False,
    )


@pytest.fixture()
def session(in_memory_session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = in_memory_session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def repository() -> AlertRuleRepository:
    return AlertRuleRepository()


def test_rule_triggered_on_event(
    app: FastAPI,
    session: Session,
    repository: AlertRuleRepository,
) -> None:
    rule = AlertRule(name="Price spike", symbol="BTC", expression="price > moving_average")

    async def _run() -> None:
        await repository.add_rule(session, rule)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/events",
                json={"symbol": "BTC", "price": 120.0, "volume": 10.0},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["triggered"] is True
        assert len(body["triggers"]) == 1
        assert body["triggers"][0]["rule_id"] == rule.id

    asyncio.run(_run())

    publisher: DummyPublisher = app.state.clients[2]
    assert len(publisher.published_payloads) == 1
    assert publisher.published_payloads[0]["rule_id"] == rule.id


def test_rule_not_triggered_when_condition_false(
    app: FastAPI,
    session: Session,
    repository: AlertRuleRepository,
) -> None:
    rule = AlertRule(name="Price drop", symbol="BTC", expression="price < moving_average")

    async def _run() -> None:
        await repository.add_rule(session, rule)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/events",
                json={"symbol": "BTC", "price": 150.0, "volume": 5.0},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["triggered"] is False
        assert body["triggers"] == []

    asyncio.run(_run())


def test_periodic_evaluation_creates_triggers(
    in_memory_session_factory: sessionmaker[Session],
) -> None:
    market_client = FakeMarketDataClient({"moving_average": 10.0, "price": 15.0})
    reports_client = FakeReportsClient({})
    publisher = DummyPublisher()
    repository = AlertRuleRepository()
    evaluator = RuleEvaluator()
    engine = AlertEngine(
        repository=repository,
        evaluator=evaluator,
        market_client=market_client,
        reports_client=reports_client,
        publisher=publisher,
        evaluation_interval=0.05,
    )

    async def _run() -> None:
        session = in_memory_session_factory()
        try:
            await repository.add_rule(
                session,
                AlertRule(name="Snapshot", symbol="ETH", expression="price > moving_average"),
            )
        finally:
            session.close()

        await engine.start_periodic_evaluation(in_memory_session_factory)
        await asyncio.sleep(0.2)
        await engine.stop()

    asyncio.run(_run())

    assert len(publisher.published_payloads) >= 1
