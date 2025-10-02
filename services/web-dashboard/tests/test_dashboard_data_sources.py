from __future__ import annotations

from datetime import datetime, timedelta

import httpx
import pytest

from schemas.order_router import (
    ExecutionRecord,
    OrderRecord,
    OrdersLogMetadata,
    PaginatedOrders,
    PositionHolding,
    PortfolioSnapshot,
    PositionsResponse,
)

from .utils import load_dashboard_app

load_dashboard_app()

from web_dashboard.app import data
from web_dashboard.app.schemas import (
    InPlayDashboardSetups,
    PerformanceMetrics,
)


@pytest.fixture(autouse=True)
def _isolate_external_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub out external integrations not covered by the tests."""

    monkeypatch.setattr(data, "_fetch_alerts_from_engine", lambda: [])
    monkeypatch.setattr(data, "_fetch_performance_metrics", lambda: PerformanceMetrics(available=False))
    monkeypatch.setattr(data, "load_reports_list", lambda: [])
    monkeypatch.setattr(
        data,
        "_fetch_inplay_setups",
        lambda: InPlayDashboardSetups(watchlists=[], fallback_reason=None),
    )
    monkeypatch.setattr(data, "_build_strategy_statuses", lambda: ([], []))


def _build_sample_order(now: datetime | None = None) -> PaginatedOrders:
    reference = now or datetime.utcnow()
    execution = ExecutionRecord(
        id=1,
        order_id=1,
        external_execution_id="fill-1",
        correlation_id=None,
        account_id="alpha",
        symbol="AAPL",
        quantity=2.0,
        price=181.25,
        fees=0.1,
        liquidity="added",
        executed_at=reference,
        created_at=reference,
    )
    order = OrderRecord(
        id=1,
        external_order_id="ORD-1",
        correlation_id=None,
        account_id="alpha",
        broker="ib",
        venue="NASDAQ",
        symbol="AAPL",
        side="BUY",
        order_type="market",
        quantity=2.0,
        filled_quantity=2.0,
        limit_price=None,
        stop_price=None,
        status="filled",
        time_in_force="DAY",
        submitted_at=reference - timedelta(minutes=5),
        expires_at=None,
        notes=None,
        created_at=reference - timedelta(minutes=6),
        updated_at=reference,
        executions=[execution],
    )
    metadata = OrdersLogMetadata(limit=100, offset=0, total=1)
    return PaginatedOrders(items=[order], metadata=metadata)


def test_dashboard_context_uses_order_router_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    paginated = _build_sample_order()
    positions = PositionsResponse(
        items=[
            PortfolioSnapshot(
                id="portfolio-alpha",
                name="Alpha",
                owner="alpha",
                total_value=362.5,
                holdings=[
                    PositionHolding(
                        id="position-alpha-aapl",
                        portfolio_id="portfolio-alpha",
                        portfolio="alpha",
                        account_id="alpha",
                        symbol="AAPL",
                        quantity=2.0,
                        average_price=181.25,
                        current_price=181.25,
                        market_value=362.5,
                    )
                ],
            )
        ],
        as_of=datetime.utcnow(),
    )

    class DummyOrderRouterClient:
        def __init__(self, *args, **kwargs):
            self.limit: int | None = None
            self.positions_called = False

        def __enter__(self) -> "DummyOrderRouterClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def close(self) -> None:
            return None

        def fetch_orders(self, *, limit: int = 100, offset: int = 0) -> PaginatedOrders:
            self.limit = limit
            return paginated

        def fetch_positions(self) -> PositionsResponse:
            self.positions_called = True
            return positions

    dummy_client = DummyOrderRouterClient()
    monkeypatch.setattr(data, "OrderRouterClient", lambda *args, **kwargs: dummy_client)

    context = data.load_dashboard_context()

    assert context.data_sources.get("portfolios") == "live"
    assert context.data_sources.get("transactions") == "live"
    names = {portfolio.name for portfolio in context.portfolios}
    assert "Growth" not in names
    assert "Income" not in names
    assert context.portfolios, "Expected at least one portfolio from order router"
    assert context.portfolios[0].owner == "alpha"
    assert any(holding.symbol == "AAPL" for holding in context.portfolios[0].holdings)
    assert context.portfolios[0].holdings[0].id is not None
    assert dummy_client.positions_called

    symbols = {transaction.symbol for transaction in context.transactions}
    assert "BTC-USD" not in symbols
    assert "AAPL" in symbols


def test_dashboard_context_falls_back_when_order_router_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    request = httpx.Request("GET", "http://order-router/orders/log")

    class FailingOrderRouterClient:
        def __enter__(self) -> "FailingOrderRouterClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def close(self) -> None:
            return None

        def fetch_orders(self, *, limit: int = 100, offset: int = 0) -> PaginatedOrders:
            raise httpx.ConnectError("unreachable", request=request)

        def fetch_positions(self) -> PositionsResponse:
            raise httpx.ConnectError("unreachable", request=request)

    monkeypatch.setattr(data, "OrderRouterClient", lambda *args, **kwargs: FailingOrderRouterClient())

    context = data.load_dashboard_context()

    assert context.data_sources.get("portfolios") == "fallback"
    assert context.data_sources.get("transactions") == "fallback"
    names = {portfolio.name for portfolio in context.portfolios}
    assert "Growth" in names
    assert any(tx.symbol == "BTC-USD" for tx in context.transactions)
