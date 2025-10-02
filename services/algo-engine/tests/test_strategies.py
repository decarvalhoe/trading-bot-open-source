from pathlib import Path
from typing import Dict

import pytest
from fastapi.testclient import TestClient
from libs.entitlements.client import Entitlements

from algo_engine.app.main import (
    StrategyRecord,
    StrategyStatus,
    _enforce_entitlements,
    app,
    orchestrator,
    strategy_repository,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_create_and_list_strategies():
    client = TestClient(app)
    payload: Dict[str, object] = {
        "name": "Morning Breakout",
        "strategy_type": "orb",
        "parameters": {"opening_range_minutes": 15},
        "enabled": True,
        "tags": ["intraday", "momentum"],
    }
    response = client.post("/strategies", json=payload)
    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "Morning Breakout"
    assert created["status"] == "PENDING"

    response = client.get("/strategies")
    assert response.status_code == 200
    body = response.json()
    assert any(item["id"] == created["id"] for item in body["items"])
    assert any(item["status"] == "PENDING" for item in body["items"])
    assert "orb" in body["available"]


def test_update_strategy_and_state_flow():
    client = TestClient(app)
    create_resp = client.post(
        "/strategies",
        json={"name": "Gap Fader", "strategy_type": "gap_fill"},
    )
    assert create_resp.status_code == 201
    strategy_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/strategies/{strategy_id}",
        json={"parameters": {"gap_pct": 1.5}, "enabled": True},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["parameters"]["gap_pct"] == 1.5

    state_resp = client.put("/state", json={"mode": "live", "daily_trade_limit": 50})
    assert state_resp.status_code == 200
    assert state_resp.json()["mode"] == "live"
    assert state_resp.json()["daily_trade_limit"] == 50

    get_state = client.get("/state")
    assert get_state.status_code == 200
    assert get_state.json()["mode"] == "live"


def test_enforce_entitlements_respects_limit():
    class DummyRequest:
        def __init__(self):
            self.state = type("S", (), {})()

    dummy_request = DummyRequest()
    dummy_request.state.entitlements = Entitlements(
        customer_id="cust-1",
        features={"can.manage_strategies": True},
        quotas={"max_active_strategies": 1},
    )

    strategy_repository.create(
        StrategyRecord(
            id="existing",
            name="Existing",
            strategy_type="orb",
            parameters={},
            enabled=True,
        )
    )

    with pytest.raises(Exception) as exc:
        _enforce_entitlements(dummy_request, True)
    assert "limit" in str(exc.value)


def test_declarative_strategy_import_export_and_backtest():
    client = TestClient(app)
    content = """
STRATEGY = {
    "name": "Python Breakout",
    "rules": [
        {
            "when": {"field": "close", "operator": "gt", "value": 100},
            "signal": {"action": "buy", "size": 1}
        },
        {
            "when": {"field": "close", "operator": "lt", "value": 95},
            "signal": {"action": "sell", "size": 1}
        }
    ],
    "parameters": {"timeframe": "1h"}
}
"""
    resp = client.post(
        "/strategies/import",
        json={"format": "python", "content": content, "tags": ["declarative"]},
    )
    assert resp.status_code == 201
    created = resp.json()
    assert created["strategy_type"] == "declarative"
    strategy_id = created["id"]

    export = client.get(f"/strategies/{strategy_id}/export", params={"fmt": "python"})
    assert export.status_code == 200
    assert "STRATEGY" in export.json()["content"]

    market_data = [
        {"close": 101},
        {"close": 103},
        {"close": 90},
        {"close": 96},
    ]
    backtest = client.post(
        f"/strategies/{strategy_id}/backtest",
        json={"market_data": market_data, "initial_balance": 1000},
    )
    assert backtest.status_code == 200
    summary = backtest.json()
    assert "total_return" in summary
    assert summary["trades"] >= 1

    strategy = client.get(f"/strategies/{strategy_id}")
    assert strategy.status_code == 200
    assert strategy.json()["last_backtest"]["metrics_path"]

    state = client.get("/state")
    assert state.status_code == 200
    assert state.json()["mode"] == "simulation"
    assert state.json()["last_simulation"]["strategy_name"] == "Python Breakout"

    backtest_dir = PACKAGE_ROOT.parents[1] / "data" / "backtests"
    assert backtest_dir.exists()
    assert any(backtest_dir.iterdir())


def test_backtest_ui_metrics_and_history():
    client = TestClient(app)
    content = """
STRATEGY = {
    "name": "Declarative Breakout",
    "rules": [
        {
            "when": {"field": "close", "operator": "gt", "value": 95},
            "signal": {"action": "buy", "size": 1}
        },
        {
            "when": {"field": "close", "operator": "lt", "value": 92},
            "signal": {"action": "sell", "size": 1}
        }
    ],
    "parameters": {"timeframe": "1h"}
}
"""
    response = client.post(
        "/strategies/import",
        json={"format": "python", "content": content, "tags": ["declarative"]},
    )
    assert response.status_code == 201
    strategy_id = response.json()["id"]

    market_data = [
        {"close": 90},
        {"close": 110},
        {"close": 92},
        {"close": 120},
    ]

    for run in range(3):
        backtest_response = client.post(
            f"/strategies/{strategy_id}/backtest",
            json={
                "market_data": market_data,
                "initial_balance": 1_000.0,
                "metadata": {"symbol": "BTCUSDT", "timeframe": "1h", "run": run},
            },
        )
        assert backtest_response.status_code == 200

    ui_metrics = client.get(f"/strategies/{strategy_id}/backtest/ui")
    assert ui_metrics.status_code == 200
    ui_payload = ui_metrics.json()
    assert ui_payload["strategy_id"] == strategy_id
    assert ui_payload["pnl"] != 0
    assert ui_payload["drawdown"] >= 0
    assert isinstance(ui_payload["equity_curve"], list)
    assert ui_payload["metadata"]["symbol"] == "BTCUSDT"

    history = client.get(
        f"/strategies/{strategy_id}/backtests",
        params={"page": 1, "page_size": 2},
    )
    assert history.status_code == 200
    history_payload = history.json()
    assert history_payload["total"] == 3
    assert len(history_payload["items"]) == 2
    assert history_payload["items"][0]["metadata"]["symbol"] == "BTCUSDT"
    assert history_payload["items"][0]["ran_at"]


def test_strategy_status_transitions():
    client = TestClient(app)
    create_resp = client.post("/strategies", json={"name": "Status Test", "strategy_type": "orb"})
    assert create_resp.status_code == 201
    data = create_resp.json()
    assert data["status"] == StrategyStatus.PENDING.value

    strategy_id = data["id"]

    activate = client.post(f"/strategies/{strategy_id}/status", json={"status": "ACTIVE"})
    assert activate.status_code == 200
    assert activate.json()["status"] == StrategyStatus.ACTIVE.value
    assert activate.json()["last_error"] is None

    failure = client.post(
        f"/strategies/{strategy_id}/status",
        json={"status": "ERROR", "error": "Execution failed"},
    )
    assert failure.status_code == 200
    assert failure.json()["status"] == StrategyStatus.ERROR.value
    assert failure.json()["last_error"] == "Execution failed"

    invalid = client.post(f"/strategies/{strategy_id}/status", json={"status": "PENDING"})
    assert invalid.status_code == 400
    assert "Invalid status transition" in invalid.json()["detail"]

def test_build_execution_plan():
    client = TestClient(app)
    response = client.post(
        "/mvp/plan",
        json={
            "broker": "binance",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "limit",
            "quantity": 0.5,
            "price": 30_000,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["order"]["broker"] == "binance"
    assert body["orderbook"]["symbol"] == "BTCUSDT"
