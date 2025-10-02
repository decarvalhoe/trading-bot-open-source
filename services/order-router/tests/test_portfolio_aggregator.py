from datetime import datetime, timezone
from decimal import Decimal

import pytest

from infra.trading_models import Execution as ExecutionModel, Order as OrderModel


class DummyClient:
    def __init__(self) -> None:
        self.enabled = True
        self.payloads: list[dict[str, object]] = []

    def publish(self, payload: dict[str, object]) -> None:
        self.payloads.append(payload)


def _build_order(
    *,
    account_id: str,
    symbol: str,
    side: str,
    quantity: float,
    price: float,
) -> OrderModel:
    order = OrderModel(
        external_order_id=f"order-{account_id}-{symbol}",
        correlation_id="corr-1",
        account_id=account_id,
        broker="binance",
        venue="binance.spot",
        symbol=symbol,
        side=side,
        order_type="limit",
        quantity=Decimal(str(quantity)),
        filled_quantity=Decimal(str(quantity)),
        limit_price=Decimal(str(price)),
        status="filled",
        time_in_force="GTC",
        submitted_at=datetime.now(tz=timezone.utc),
    )
    execution = ExecutionModel(
        order=order,
        external_execution_id=f"exec-{account_id}-{symbol}",
        correlation_id="corr-1",
        account_id=account_id,
        symbol=symbol,
        quantity=Decimal(str(quantity)),
        price=Decimal(str(price)),
        executed_at=datetime.now(tz=timezone.utc),
    )
    return order


@pytest.fixture()
def aggregator_cls(app_module):
    return app_module.PortfolioAggregator


@pytest.fixture()
def publisher_cls(app_module):
    return app_module.StreamingOrderEventsPublisher


def test_portfolio_aggregator_computes_holdings(aggregator_cls):
    aggregator = aggregator_cls()
    assert not aggregator.snapshot()

    aggregator.apply_fill(
        account_id="alpha_trader",
        symbol="AAPL",
        side="buy",
        quantity=5,
        price=100,
    )
    aggregator.apply_fill(
        account_id="alpha_trader",
        symbol="AAPL",
        side="sell",
        quantity=2,
        price=110,
    )
    aggregator.apply_fill(
        account_id="alpha_trader",
        symbol="MSFT",
        side="buy",
        quantity=3,
        price=50,
    )

    snapshot = aggregator.snapshot()
    assert len(snapshot) == 1
    portfolio = snapshot[0]
    assert portfolio["owner"] == "alpha_trader"
    assert portfolio["name"] == "Alpha Trader"
    assert pytest.approx(portfolio["total_value"], rel=1e-6) == 480.0

    holdings = {holding["symbol"]: holding for holding in portfolio["holdings"]}
    assert set(holdings) == {"AAPL", "MSFT"}
    assert pytest.approx(holdings["AAPL"]["quantity"], rel=1e-6) == 3.0
    assert pytest.approx(holdings["AAPL"]["average_price"], rel=1e-6) == pytest.approx(
        720 / 7
    )
    assert pytest.approx(holdings["AAPL"]["current_price"], rel=1e-6) == 110.0
    assert pytest.approx(holdings["MSFT"]["quantity"], rel=1e-6) == 3.0
    assert pytest.approx(holdings["MSFT"]["market_value"], rel=1e-6) == 150.0


def test_reload_state_publishes_snapshot(db_session, publisher_cls):
    order = _build_order(
        account_id="acct-reload",
        symbol="BTCUSDT",
        side="buy",
        quantity=1.5,
        price=30_500,
    )
    db_session.add(order)
    db_session.flush()

    client = DummyClient()
    publisher = publisher_cls(client)
    publisher.reload_state(db_session)

    assert client.payloads, "Expected a portfolio snapshot to be published"
    snapshot = client.payloads[-1]
    assert snapshot["resource"] == "portfolios"
    assert snapshot["mode"] == "live"
    assert snapshot["items"]
    portfolio = snapshot["items"][0]
    assert portfolio["owner"] == "acct-reload"
    assert pytest.approx(portfolio["total_value"], rel=1e-6) == pytest.approx(1.5 * 30_500)
