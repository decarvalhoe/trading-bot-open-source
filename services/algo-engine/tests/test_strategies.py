import importlib.util
import os
import sys
from pathlib import Path
from typing import Dict

import pytest
from fastapi.testclient import TestClient
from libs.entitlements.client import Entitlements

os.environ.setdefault("ENTITLEMENTS_BYPASS", "1")

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
_enforce_entitlements = main_module._enforce_entitlements


@pytest.fixture(autouse=True)
def reset_state():
    store._strategies.clear()  # type: ignore[attr-defined]
    orchestrator.update_daily_limit(trades_submitted=0)
    orchestrator.set_mode("paper")
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

    response = client.get("/strategies")
    assert response.status_code == 200
    body = response.json()
    assert any(item["id"] == created["id"] for item in body["items"])
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
