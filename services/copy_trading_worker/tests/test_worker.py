from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from infra import Listing, MarketplaceBase, MarketplaceSubscription
from schemas.market import ExecutionFill, ExecutionReport, ExecutionStatus, ExecutionVenue, OrderSide
from schemas.order_router import ExecutionIntent

from services.copy_trading_worker.app.events import LeaderExecutionEvent
from services.copy_trading_worker.app.messaging import InMemoryLeaderExecutionBroker
from services.copy_trading_worker.app.repository import CopySubscriptionRepository
from services.copy_trading_worker.app.worker import CopyTradingWorker, OrderExecutionClient


@pytest.fixture()
def database(tmp_path: Any) -> Session:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path}/copy_trading.db",
        connect_args={"check_same_thread": False},
        future=True,
    )
    MarketplaceBase.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    try:
        yield SessionLocal
    finally:
        MarketplaceBase.metadata.drop_all(bind=engine)
        engine.dispose()


class DummyOrderExecutor(OrderExecutionClient):
    def __init__(self, report: ExecutionReport) -> None:
        self._report = report
        self.submitted: list[ExecutionIntent] = []
        self.invocations = asyncio.Event()

    async def submit_order(self, intent: ExecutionIntent) -> ExecutionReport:
        self.submitted.append(intent)
        self.invocations.set()
        return self._report


class FailingOrderExecutor(OrderExecutionClient):
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.submitted: list[ExecutionIntent] = []
        self.invocations = asyncio.Event()

    async def submit_order(self, intent: ExecutionIntent) -> ExecutionReport:  # type: ignore[override]
        self.submitted.append(intent)
        self.invocations.set()
        raise self.error


def _seed_subscription(
    session_factory: sessionmaker,
    *,
    listing_id: int = 1,
    owner_id: str = "leader-1",
    strategy_name: str = "Momentum Edge",
    follower_id: str = "follower-1",
    leverage: float = 2.0,
    allocated_capital: float | None = 5_000.0,
    risk_limits: dict[str, Any] | None = None,
) -> int:
    with session_factory() as session:
        listing = Listing(
            id=listing_id,
            owner_id=owner_id,
            strategy_name=strategy_name,
            description="",
            price_cents=10000,
            currency="USD",
            connect_account_id="acct_leader",
            status="approved",
        )
        session.add(listing)
        subscription = MarketplaceSubscription(
            listing=listing,
            subscriber_id=follower_id,
            status="active",
            leverage=leverage,
            allocated_capital=allocated_capital,
            risk_limits=risk_limits or {},
            replication_status="idle",
        )
        session.add(subscription)
        session.commit()
        return subscription.id


def _build_execution_report(quantity: float, price: float) -> ExecutionReport:
    timestamp = datetime.now(timezone.utc)
    return ExecutionReport(
        order_id="ORD-1",
        status=ExecutionStatus.FILLED,
        broker="ib",
        venue=ExecutionVenue.IBKR_PAPER,
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=quantity,
        filled_quantity=quantity,
        avg_price=price,
        submitted_at=timestamp,
        fills=[ExecutionFill(quantity=quantity, price=price, timestamp=timestamp)],
        tags=["strategy:Momentum Edge"],
    )


def test_replication_nominal_flow(database: sessionmaker) -> None:
    async def _run() -> None:
        subscription_id = _seed_subscription(
            database,
            risk_limits={"max_notional": 4_000},
        )
        broker = InMemoryLeaderExecutionBroker()
        follower_report = _build_execution_report(quantity=20, price=101.0)
        executor = DummyOrderExecutor(follower_report)
        repository = CopySubscriptionRepository(session_factory=database)
        worker = CopyTradingWorker(
            consumer=broker,
            order_executor=executor,
            repository=repository,
            clock=lambda: datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

        leader_report = _build_execution_report(quantity=10, price=100.0)
        event = LeaderExecutionEvent(
            leader_id="leader-1",
            strategy="Momentum Edge",
            report=leader_report,
            fees=12.5,
        )

        task = asyncio.create_task(worker.run_forever())
        await broker.publish(event)
        await asyncio.wait_for(executor.invocations.wait(), timeout=2)
        await worker.stop()
        await asyncio.wait_for(task, timeout=2)

        assert executor.submitted, "expected follower order to be routed"
        submitted_intent = executor.submitted[0]
        assert submitted_intent.account_id == "follower-1"
        assert pytest.approx(submitted_intent.quantity, rel=1e-6) == 20.0
        assert "copy:follower" in submitted_intent.tags
        assert f"copy:subscription:{subscription_id}" in submitted_intent.tags

        with database() as session:
            stored = session.get(MarketplaceSubscription, subscription_id)
            assert stored is not None
            assert stored.replication_status == ExecutionStatus.FILLED.value
            assert stored.last_synced_at == datetime(2024, 1, 1, tzinfo=timezone.utc)
            assert stored.divergence_bps is not None
            assert stored.divergence_bps == pytest.approx(100.0)
            assert stored.total_fees_paid == pytest.approx(25.25, rel=1e-6)

    asyncio.run(_run())


def test_replication_error_updates_status(database: sessionmaker) -> None:
    async def _run() -> None:
        subscription_id = _seed_subscription(database)
        broker = InMemoryLeaderExecutionBroker()
        executor = FailingOrderExecutor(RuntimeError("router down"))
        repository = CopySubscriptionRepository(session_factory=database)
        worker = CopyTradingWorker(
            consumer=broker,
            order_executor=executor,
            repository=repository,
            clock=lambda: datetime(2024, 2, 1, tzinfo=timezone.utc),
        )

        event = LeaderExecutionEvent(
            leader_id="leader-1",
            strategy="Momentum Edge",
            report=_build_execution_report(quantity=5, price=50.0),
        )

        task = asyncio.create_task(worker.run_forever())
        await broker.publish(event)
        await asyncio.wait_for(executor.invocations.wait(), timeout=2)
        await worker.stop()
        await asyncio.wait_for(task, timeout=2)

        with database() as session:
            stored = session.get(MarketplaceSubscription, subscription_id)
            assert stored is not None
            assert stored.replication_status == "error"
            assert stored.total_fees_paid == pytest.approx(0.0)

    asyncio.run(_run())


def test_worker_stops_without_events(database: sessionmaker) -> None:
    async def _run() -> None:
        _seed_subscription(database)
        broker = InMemoryLeaderExecutionBroker()
        executor = DummyOrderExecutor(_build_execution_report(quantity=1, price=1.0))
        repository = CopySubscriptionRepository(session_factory=database)
        worker = CopyTradingWorker(
            consumer=broker,
            order_executor=executor,
            repository=repository,
        )

        task = asyncio.create_task(worker.run_forever())
        await worker.stop()
        await asyncio.wait_for(task, timeout=2)

        assert not executor.submitted

    asyncio.run(_run())
