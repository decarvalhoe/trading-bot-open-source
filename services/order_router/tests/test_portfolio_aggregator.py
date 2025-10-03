from datetime import datetime, timezone
from decimal import Decimal

import pytest

from infra.trading_models import Execution as ExecutionModel, Order as OrderModel
from schemas.market import (
    ExecutionFill,
    ExecutionReport,
    ExecutionStatus,
    ExecutionVenue,
    OrderSide,
    OrderType,
)
from schemas.order_router import ExecutionIntent
from libs.portfolio import encode_portfolio_key, encode_position_key


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
    assert portfolio["id"] == encode_portfolio_key("alpha_trader")

    holdings = {holding["symbol"]: holding for holding in portfolio["holdings"]}
    assert set(holdings) == {"AAPL", "MSFT"}
    assert holdings["AAPL"]["id"] == encode_position_key("alpha_trader", "AAPL")
    assert holdings["AAPL"]["portfolio_id"] == portfolio["id"]
    assert holdings["AAPL"]["portfolio"] == "alpha_trader"
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
    assert snapshot.get("type") == "positions"
    assert snapshot["items"]
    portfolio = snapshot["items"][0]
    assert portfolio["owner"] == "acct-reload"
    assert portfolio["id"] == encode_portfolio_key("acct-reload")
    assert pytest.approx(portfolio["total_value"], rel=1e-6) == pytest.approx(1.5 * 30_500)


def test_simulated_execution_streams_virtual_portfolios(publisher_cls):
    client = DummyClient()
    publisher = publisher_cls(client)
    timestamp = datetime.now(timezone.utc)
    report = ExecutionReport(
        order_id="SIM-TEST",
        status=ExecutionStatus.FILLED,
        broker="binance",
        venue=ExecutionVenue.BINANCE_SPOT,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=1.0,
        filled_quantity=1.0,
        avg_price=25_000.0,
        submitted_at=timestamp,
        fills=[ExecutionFill(quantity=1.0, price=25_000.0, timestamp=timestamp)],
        tags=["strategy:test"],
    )
    order = ExecutionIntent(
        broker="binance",
        venue="binance.spot",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=1.0,
        price=25_000.0,
        tags=["strategy:test"],
    )

    publisher.simulated_execution(order, report, "sim-account")

    resources = {payload["resource"] for payload in client.payloads}
    assert {"transactions", "logs", "portfolios"}.issubset(resources)

    transaction_payload = next(
        payload for payload in client.payloads if payload["resource"] == "transactions"
    )
    transaction = transaction_payload["items"][0]
    assert transaction["mode"] == "dry_run"
    assert transaction.get("simulated") is True

    log_payload = next(
        payload for payload in client.payloads if payload["resource"] == "logs"
    )
    entry = log_payload.get("entry") or log_payload.get("items", [{}])[0]
    assert entry["mode"] == "dry_run"
    assert entry.get("simulated") is True
    assert entry["status"].startswith("SIMULATED")

    portfolio_payload = next(
        payload for payload in client.payloads if payload["resource"] == "portfolios"
    )
    assert portfolio_payload["mode"] == "dry_run"
    assert portfolio_payload.get("type") == "positions"
    assert portfolio_payload["items"], "Expected virtual holdings to be published"
