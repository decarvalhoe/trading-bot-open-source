import importlib.util
import os
import sys
from pathlib import Path
from typing import Dict
import types

import pytest
from fastapi.testclient import TestClient
from libs.entitlements.client import Entitlements

os.environ.setdefault("ENTITLEMENTS_BYPASS", "1")

prometheus_stub = types.ModuleType("prometheus_client")


class _DummyMetric:
    def __init__(self, *args, **kwargs):  # noqa: D401 - mimic Prometheus signature
        """No-op metric"""

    def labels(self, *args, **kwargs):
        return self

    def inc(self, *args, **kwargs) -> None:
        return None

    def observe(self, *args, **kwargs) -> None:
        return None


prometheus_stub.CONTENT_TYPE_LATEST = "text/plain"
prometheus_stub.Counter = _DummyMetric
prometheus_stub.Histogram = _DummyMetric
prometheus_stub.generate_latest = lambda: b""  # type: ignore[assignment]
sys.modules.setdefault("prometheus_client", prometheus_stub)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _load_package(alias: str, path: Path) -> None:
    spec = importlib.util.spec_from_file_location(alias, path / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    module.__path__ = [str(path)]  # type: ignore[attr-defined]
    sys.modules[alias] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[attr-defined]


_load_package("algo_engine", PACKAGE_ROOT)
_load_package("algo_engine.app", PACKAGE_ROOT / "app")
_load_package("algo_engine.app.strategies", PACKAGE_ROOT / "app" / "strategies")

main_spec = importlib.util.spec_from_file_location("algo_engine.app.main", PACKAGE_ROOT / "app" / "main.py")
main_module = importlib.util.module_from_spec(main_spec)
sys.modules["algo_engine.app.main"] = main_module
assert main_spec and main_spec.loader
main_spec.loader.exec_module(main_module)  # type: ignore[attr-defined]

app = main_module.app
store = main_module.store
orchestrator = main_module.orchestrator
StrategyRecord = main_module.StrategyRecord
StrategyStatus = main_module.StrategyStatus
_enforce_entitlements = main_module._enforce_entitlements


@pytest.fixture(autouse=True)
def reset_state():
    store._strategies.clear()  # type: ignore[attr-defined]
    orchestrator.update_daily_limit(trades_submitted=0)
    orchestrator.set_mode("paper")
    orchestrator._state.last_simulation = None  # type: ignore[attr-defined]
    yield


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

    store.create(
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
