from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from services.alert_engine.app.cache import AlertContextCache
from services.alert_engine.app.clients import MarketDataStreamClient
from services.alert_engine.app.database import Base
from services.alert_engine.app.engine import AlertEngine
from services.alert_engine.app.evaluator import RuleEvaluator
from services.alert_engine.app.models import AlertRule
from services.alert_engine.app.repository import AlertRuleRepository
from services.alert_engine.app.streaming import StreamProcessor
from services.alert_engine.tests.test_alert_engine import (  # noqa: TID252
    DummyPublisher,
    FakeMarketDataClient,
    FakeReportsClient,
)


class InMemoryStreamClient(MarketDataStreamClient):
    def __init__(self) -> None:
        self._own_client = False
        self._client = None
        self._queues: dict[str, asyncio.Queue[dict[str, float]]] = {}

    async def subscribe(self, symbol: str) -> AsyncIterator[dict[str, float]]:  # type: ignore[override]
        queue = self._queues.setdefault(symbol, asyncio.Queue())
        while True:
            payload = await queue.get()
            yield payload

    async def publish(self, symbol: str, payload: dict[str, float]) -> None:
        queue = self._queues.setdefault(symbol, asyncio.Queue())
        await queue.put(payload)

    async def aclose(self) -> None:  # pragma: no cover - interface requirement
        for queue in self._queues.values():
            while not queue.empty():
                queue.get_nowait()
        self._queues.clear()


@pytest.fixture()
def stream_session_factory() -> Iterator[sessionmaker[Session]]:
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


def test_stream_processing_triggers_alert(stream_session_factory: sessionmaker[Session]) -> None:
    market_client = FakeMarketDataClient({"moving_average": 100.0})
    reports_client = FakeReportsClient({"daily_volume": 4000})
    context_cache = AlertContextCache(
        market_client=market_client,
        reports_client=reports_client,
        market_ttl_seconds=60.0,
        event_ttl_seconds=10.0,
        reports_ttl_seconds=300.0,
    )
    publisher = DummyPublisher()
    repository = AlertRuleRepository()
    evaluator = RuleEvaluator()
    engine = AlertEngine(
        repository=repository,
        evaluator=evaluator,
        context_cache=context_cache,
        publisher=publisher,
        evaluation_interval=0.1,
    )

    stream_client = InMemoryStreamClient()
    processor = StreamProcessor(
        stream_client=stream_client, engine=engine, session_factory=stream_session_factory
    )

    rule = AlertRule(name="Spike", symbol="BTC", expression="price > moving_average")

    session = stream_session_factory()
    try:
        asyncio.run(repository.add_rule(session, rule))
    finally:
        session.close()

    async def _run() -> None:
        await processor.start(["BTC"])
        await stream_client.publish("BTC", {"price": 125.0, "volume": 5.0})
        await asyncio.sleep(0.2)
        await processor.stop()

    asyncio.run(_run())

    assert publisher.published_payloads, "Stream processor should publish an alert payload"

    session = stream_session_factory()
    try:
        triggers = asyncio.run(repository.list_recent_triggers(session, limit=1))
    finally:
        session.close()
    assert triggers and triggers[0].rule_id == rule.id
