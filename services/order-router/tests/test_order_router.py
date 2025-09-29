"""Integration tests for the order router service."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import pytest

from infra.trading_models import Execution as ExecutionModel, Order as OrderModel


DEFAULT_ORDER: Dict[str, Any] = {
    "broker": "binance",
    "venue": "binance.spot",
    "symbol": "BTCUSDT",
    "side": "buy",
    "order_type": "limit",
    "quantity": 0.5,
    "price": 30_000,
}


def _submit_order(client, **overrides: Any) -> Dict[str, Any]:
    payload = DEFAULT_ORDER | overrides
    response = client.post("/orders", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _parse_timestamp(value: str | None) -> datetime:
    assert value is not None, "timestamp must be present"
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


@pytest.mark.usefixtures("clean_database")
def test_order_persistence_and_filters(client, db_session):
    first = _submit_order(client, account_id="acct-1")
    second = _submit_order(
        client, symbol="ETHUSDT", price=2_000, account_id="acct-2"
    )
    third = _submit_order(
        client, symbol="BTCUSDT", quantity=0.2, price=31_000, account_id="acct-1"
    )

    db_session.expire_all()
    stored_orders = db_session.query(OrderModel).order_by(OrderModel.created_at).all()
    assert len(stored_orders) == 3
    assert {order.account_id for order in stored_orders} == {"acct-1", "acct-2"}
    assert {order.symbol for order in stored_orders} >= {"BTCUSDT", "ETHUSDT"}

    account_filtered = client.get("/orders/log", params={"account_id": "acct-1"})
    assert account_filtered.status_code == 200
    account_payload = account_filtered.json()
    assert account_payload["metadata"]["total"] == 2
    assert all(item["account_id"] == "acct-1" for item in account_payload["items"])

    symbol_filtered = client.get("/orders/log", params={"symbol": "ETHUSDT"})
    assert symbol_filtered.status_code == 200
    symbol_payload = symbol_filtered.json()
    assert symbol_payload["metadata"]["total"] == 1
    assert all(item["symbol"] == "ETHUSDT" for item in symbol_payload["items"])

    start_time = _parse_timestamp(second["submitted_at"])
    start_filtered = client.get("/orders/log", params={"start": start_time.isoformat()})
    assert start_filtered.status_code == 200
    start_payload = start_filtered.json()
    assert start_payload["metadata"]["total"] == 2
    for item in start_payload["items"]:
        submitted = item.get("submitted_at") or item["created_at"]
        assert _parse_timestamp(submitted) >= start_time

    end_time = _parse_timestamp(first["submitted_at"])
    end_filtered = client.get("/orders/log", params={"end": end_time.isoformat()})
    assert end_filtered.status_code == 200
    end_payload = end_filtered.json()
    for item in end_payload["items"]:
        submitted = item.get("submitted_at") or item["created_at"]
        assert _parse_timestamp(submitted) <= end_time


@pytest.mark.usefixtures("clean_database")
def test_cancel_order_records_cancellation(client, db_session):
    report = _submit_order(client, account_id="acct-cancel")
    cancel_response = client.post(
        f"/orders/{report['broker']}/cancel", json={"order_id": report["order_id"]}
    )
    assert cancel_response.status_code == 200
    cancel_payload = cancel_response.json()
    assert cancel_payload["status"].lower() == "cancelled"

    db_session.expire_all()
    stored_order = (
        db_session.query(OrderModel)
        .filter(OrderModel.external_order_id == report["order_id"])
        .one()
    )
    assert stored_order.status == "cancelled"
    executions = (
        db_session.query(ExecutionModel)
        .filter(ExecutionModel.order_id == stored_order.id)
        .order_by(ExecutionModel.executed_at)
        .all()
    )
    assert len(executions) >= 2
    assert executions[-1].liquidity == "cancelled"
    assert executions[-1].quantity == 0

    log_response = client.get("/orders/log", params={"account_id": "acct-cancel"})
    assert log_response.status_code == 200
    log_payload = log_response.json()
    assert log_payload["items"][0]["status"] == "cancelled"


@pytest.mark.usefixtures("clean_database")
def test_execution_filters_by_account_symbol_and_time(client, db_session):
    first = _submit_order(client, account_id="acct-1", symbol="BTCUSDT")
    second = _submit_order(client, account_id="acct-2", symbol="ETHUSDT", price=2_000)
    third = _submit_order(
        client,
        account_id="acct-2",
        symbol="ETHUSDT",
        quantity=1.5,
        price=2_100,
    )

    db_session.expire_all()
    executions = db_session.query(ExecutionModel).all()
    assert len(executions) >= 3

    target_order = (
        db_session.query(OrderModel)
        .filter(OrderModel.external_order_id == second["order_id"])
        .one()
    )

    filtered = client.get(
        "/executions",
        params={"account_id": "acct-2", "symbol": "ETHUSDT"},
    )
    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    assert filtered_payload["metadata"]["total"] == 2
    assert all(item["symbol"] == "ETHUSDT" for item in filtered_payload["items"])
    assert all(item["account_id"] == "acct-2" for item in filtered_payload["items"])

    by_order = client.get("/executions", params={"order_id": target_order.id})
    assert by_order.status_code == 200
    by_order_payload = by_order.json()
    assert by_order_payload["metadata"]["total"] == 1
    assert all(item["order_id"] == target_order.id for item in by_order_payload["items"])

    start_time = _parse_timestamp(third["fills"][0]["timestamp"])
    start_filtered = client.get(
        "/executions", params={"start": start_time.isoformat()}
    )
    assert start_filtered.status_code == 200
    start_payload = start_filtered.json()
    for item in start_payload["items"]:
        assert _parse_timestamp(item["executed_at"]) >= start_time


def test_daily_notional_limit_enforced(client, router):
    router.update_state(limit=30_000.0)

    first = client.post(
        "/orders",
        json={
            "broker": "ibkr",
            "venue": "ibkr.paper",
            "symbol": "AAPL",
            "side": "buy",
            "order_type": "limit",
            "quantity": 200,
            "price": 100,
        },
    )
    assert first.status_code == 201

    second = client.post(
        "/orders",
        json={
            "broker": "ibkr",
            "venue": "ibkr.paper",
            "symbol": "AAPL",
            "side": "buy",
            "order_type": "limit",
            "quantity": 200,
            "price": 100,
        },
    )
    assert second.status_code == 403
    assert "Daily notional" in second.json()["detail"]


def test_risk_rule_rejection(client):
    response = client.post(
        "/orders",
        json={
            "broker": "binance",
            "venue": "binance.spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "limit",
            "quantity": 0.6,
            "price": 200_000,
        },
    )
    assert response.status_code == 400
    assert "notional" in response.json()["detail"].lower()


def test_stop_loss_alert_and_endpoint(client):
    response = client.post(
        "/orders",
        json={
            "broker": "binance",
            "venue": "binance.spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "limit",
            "quantity": 0.2,
            "price": 30_000,
            "risk": {
                "account_id": "alert-account",
                "realized_pnl": -45_000,
                "unrealized_pnl": -1_000,
                "stop_loss": 50_000,
            },
        },
    )
    assert response.status_code == 201
    alerts_resp = client.get("/risk/alerts")
    assert alerts_resp.status_code == 200
    alerts = alerts_resp.json()
    assert any(alert["rule_id"] == "stop_loss" for alert in alerts)


def test_preview_execution_plan(client):
    response = client.post(
        "/plans",
        json={
            "broker": "binance",
            "venue": "binance.spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "limit",
            "quantity": 0.5,
            "price": 30_000,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["plan"]["order"]["symbol"] == "BTCUSDT"
