"""Integration tests for the order router service."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import time
from typing import Any, Dict

import httpx
import pytest
import respx

from infra.trading_models import (
    Execution as ExecutionModel,
    Order as OrderModel,
    SimulatedExecution as SimulatedExecutionModel,
)
from libs.portfolio import decode_position_key


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


def _wait_for_calls(route, count: int, timeout: float = 1.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if route.call_count >= count:
            return
        time.sleep(0.05)
    assert route.call_count >= count, f"Expected {count} streaming calls, got {route.call_count}"


def _find_holding(items: list[dict[str, Any]], symbol: str) -> dict[str, Any] | None:
    for portfolio in items:
        for holding in portfolio.get("holdings", []):
            if holding.get("symbol") == symbol:
                return holding
    return None


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
def test_symbol_normalization(client, db_session):
    report = _submit_order(client, symbol="btc/usdt", account_id="acct-norm")
    assert report["symbol"] == "BTCUSDT"

    db_session.expire_all()
    stored = db_session.query(OrderModel).filter(OrderModel.account_id == "acct-norm").one()
    assert stored.symbol == "BTCUSDT"


@pytest.mark.usefixtures("clean_database")
def test_order_annotation_updates_notes_and_tags(client, db_session):
    report = _submit_order(
        client,
        account_id="acct-notes",
        tags=["strategy:momentum", "priority"],
    )

    order_row = (
        db_session.query(OrderModel)
        .filter(OrderModel.external_order_id == report["order_id"])
        .one()
    )

    annotation = client.post(
        f"/orders/{order_row.id}/notes",
        json={"notes": "Revue manuelle", "tags": ["follow-up", "Momentum"]},
    )
    assert annotation.status_code == 200, annotation.text
    payload = annotation.json()
    assert "Revue manuelle" in payload["notes"]
    assert any(tag.lower() == "follow-up" for tag in payload["tags"])
    assert any(tag.lower() == "strategy:momentum" for tag in payload["tags"])

    db_session.expire_all()
    stored_order = db_session.get(OrderModel, order_row.id)
    assert stored_order is not None
    assert stored_order.notes and "Revue manuelle" in stored_order.notes
    assert any(tag.lower() == "follow-up" for tag in (stored_order.tags or []))

    execution = (
        db_session.query(ExecutionModel)
        .filter(ExecutionModel.order_id == stored_order.id)
        .first()
    )
    assert execution is not None
    assert execution.notes and "Revue manuelle" in execution.notes
    assert any(tag.lower() == "follow-up" for tag in (execution.tags or []))

    tagged_orders = client.get("/orders/log", params={"tag": "follow-up"})
    assert tagged_orders.status_code == 200
    assert tagged_orders.json()["metadata"]["total"] == 1

    strategy_orders = client.get("/orders/log", params={"strategy": "momentum"})
    assert strategy_orders.status_code == 200
    assert strategy_orders.json()["metadata"]["total"] >= 1

    tagged_executions = client.get("/executions", params={"tag": "follow-up"})
    assert tagged_executions.status_code == 200
    assert tagged_executions.json()["metadata"]["total"] >= 1


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


@pytest.mark.usefixtures("clean_database")
def test_positions_endpoint_exposes_current_holdings(client):
    _submit_order(client, account_id="acct-pos", quantity=0.25, price=30_500)

    response = client.get("/positions")
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"], "Expected at least one portfolio"
    portfolio = payload["items"][0]
    holding = _find_holding(payload["items"], DEFAULT_ORDER["symbol"])
    assert holding is not None, payload
    assert holding["portfolio"] == "acct-pos"
    assert decode_position_key(holding["id"]) == ("acct-pos", DEFAULT_ORDER["symbol"])


@pytest.mark.usefixtures("clean_database")
def test_close_position_submits_market_order(client):
    _submit_order(client, account_id="acct-close", quantity=0.3, price=30_200)

    snapshot = client.get("/positions").json()["items"]
    holding = _find_holding(snapshot, DEFAULT_ORDER["symbol"])
    assert holding is not None

    close_response = client.post(f"/positions/{holding['id']}/close")
    assert close_response.status_code == 200, close_response.text
    payload = close_response.json()
    order = payload["order"]
    assert order["side"].lower() == "sell"
    assert pytest.approx(order["quantity"], rel=1e-6) == pytest.approx(0.3)
    updated = payload["positions"]["items"]
    assert _find_holding(updated, DEFAULT_ORDER["symbol"]) is None


@pytest.mark.usefixtures("clean_database")
def test_close_position_accepts_target_quantity(client):
    _submit_order(client, account_id="acct-adjust", quantity=0.5, price=30_000)

    positions = client.get("/positions").json()["items"]
    holding = _find_holding(positions, DEFAULT_ORDER["symbol"])
    assert holding is not None

    adjust_response = client.post(
        f"/positions/{holding['id']}/close", json={"target_quantity": 0.2}
    )
    assert adjust_response.status_code == 200, adjust_response.text
    payload = adjust_response.json()
    order = payload["order"]
    assert order["side"].lower() == "sell"
    assert pytest.approx(order["quantity"], rel=1e-6) == pytest.approx(0.3)
    updated_holding = _find_holding(payload["positions"]["items"], DEFAULT_ORDER["symbol"])
    assert updated_holding is not None
    assert pytest.approx(updated_holding["quantity"], rel=1e-6) == pytest.approx(0.2)


@respx.mock
@pytest.mark.usefixtures("clean_database")
def test_streaming_events_emitted_on_order_creation(client):
    route = respx.post("http://streaming.test/ingest/reports").mock(
        return_value=httpx.Response(202, json={"status": "queued"})
    )
    initial_calls = route.call_count
    report = _submit_order(
        client,
        account_id="acct-stream",
        tags=["strategy:alpha"],
    )

    _wait_for_calls(route, initial_calls + 3)

    assert route.calls, "No streaming payload captured"
    first_request = route.calls[0].request
    assert first_request.headers.get("x-service-token") == "reports-token"

    payloads = [json.loads(call.request.content) for call in route.calls]
    resources = [payload["payload"]["resource"] for payload in payloads]
    assert "transactions" in resources
    assert "logs" in resources
    assert "portfolios" in resources

    transaction_payload = next(
        payload for payload in payloads if payload["payload"]["resource"] == "transactions"
    )
    transaction = transaction_payload["payload"]["items"][0]
    assert transaction["portfolio"] == "acct-stream"
    assert transaction["symbol"] == "BTCUSDT"
    assert transaction["quantity"] == pytest.approx(report["filled_quantity"])

    log_payload = next(
        payload for payload in payloads if payload["payload"]["resource"] == "logs"
    )
    entry = log_payload["payload"].get("entry") or log_payload["payload"]["items"][0]
    assert entry["status"] == "FILLED"
    assert entry["symbol"] == "BTCUSDT"
    assert entry["message"].startswith("FILLED")
    assert log_payload["room_id"] == "public-room"
    assert log_payload["source"] == "reports"


@respx.mock
@pytest.mark.usefixtures("clean_database")
def test_streaming_event_emitted_on_cancellation(client):
    route = respx.post("http://streaming.test/ingest/reports").mock(
        return_value=httpx.Response(202, json={"status": "queued"})
    )
    report = _submit_order(client, account_id="acct-cancel")

    _wait_for_calls(route, 2)

    cancel_response = client.post(
        f"/orders/{report['broker']}/cancel", json={"order_id": report["order_id"]}
    )
    assert cancel_response.status_code == 200

    _wait_for_calls(route, 3)

    last_payload = json.loads(route.calls[-1].request.content)
    assert last_payload["payload"]["resource"] == "logs"
    entry = last_payload["payload"].get("entry") or last_payload["payload"]["items"][0]
    assert entry["status"] == "CANCELLED"
    assert entry["symbol"] == report["symbol"]
    assert "ordre" in entry["message"]


@pytest.mark.usefixtures("clean_database")
def test_dry_run_records_simulations_and_restores_state(client, db_session):
    response = client.put("/state", json={"mode": "dry_run"})
    assert response.status_code == 200, response.text

    report = _submit_order(
        client,
        account_id="sim-acct",
        quantity=0.3,
        price=25_500,
        tags=["strategy:dry-run"],
    )
    assert report["status"].lower() == "filled"

    db_session.expire_all()
    assert db_session.query(OrderModel).count() == 0
    simulations = db_session.query(SimulatedExecutionModel).all()
    assert len(simulations) == 1
    simulation = simulations[0]
    assert simulation.account_id == "sim-acct"
    assert simulation.symbol == "BTCUSDT"
    assert pytest.approx(float(simulation.filled_quantity), rel=1e-6) == 0.3
    assert pytest.approx(float(simulation.price), rel=1e-6) == 25_500
    assert any(tag.lower() == "strategy:dry-run" for tag in (simulation.tags or []))

    positions = client.get("/positions")
    assert positions.status_code == 200
    payload = positions.json()
    holding = _find_holding(payload["items"], "BTCUSDT")
    assert holding is not None
    assert holding["account_id"] == "sim-acct"
    assert pytest.approx(holding["quantity"], rel=1e-6) == 0.3
    assert pytest.approx(holding["average_price"], rel=1e-6) == 25_500

    live_switch = client.put("/state", json={"mode": "live"})
    assert live_switch.status_code == 200
    live_positions = client.get("/positions")
    assert live_positions.status_code == 200
    assert _find_holding(live_positions.json()["items"], "BTCUSDT") is None

    back_to_dry = client.put("/state", json={"mode": "dry_run"})
    assert back_to_dry.status_code == 200
    restored = client.get("/positions")
    assert restored.status_code == 200
    restored_holding = _find_holding(restored.json()["items"], "BTCUSDT")
    assert restored_holding is not None
    assert pytest.approx(restored_holding["quantity"], rel=1e-6) == pytest.approx(
        holding["quantity"], rel=1e-6
    )
    assert pytest.approx(restored_holding["average_price"], rel=1e-6) == pytest.approx(
        holding["average_price"], rel=1e-6
    )


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
