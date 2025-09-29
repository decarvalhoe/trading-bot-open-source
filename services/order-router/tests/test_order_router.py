import importlib.util
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infra.trading_models import Execution as ExecutionModel, Order as OrderModel
from libs.db.db import SessionLocal

os.environ.setdefault("ENTITLEMENTS_BYPASS", "1")

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _load_package(alias: str, path: Path) -> None:
    spec = importlib.util.spec_from_file_location(alias, path / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    module.__path__ = [str(path)]  # type: ignore[attr-defined]
    sys.modules[alias] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[attr-defined]


_load_package("order_router", PACKAGE_ROOT)
_load_package("order_router.app", PACKAGE_ROOT / "app")
_load_package("order_router.app.brokers", PACKAGE_ROOT / "app" / "brokers")

main_spec = importlib.util.spec_from_file_location("order_router.app.main", PACKAGE_ROOT / "app" / "main.py")
main_module = importlib.util.module_from_spec(main_spec)
sys.modules["order_router.app.main"] = main_module
assert main_spec and main_spec.loader
main_spec.loader.exec_module(main_module)  # type: ignore[attr-defined]

app = main_module.app
router = main_module.router


@pytest.fixture(autouse=True)
def reset_router_state():
    router._state.notional_routed = 0.0  # type: ignore[attr-defined]
    router._risk_alerts.clear()  # type: ignore[attr-defined]
    router._limit_store._positions.clear()  # type: ignore[attr-defined]
    router._limit_store._stop_losses.clear()  # type: ignore[attr-defined]
    router._limit_store.set_stop_loss("default", 50_000.0)  # type: ignore[attr-defined]
    router.update_state(mode="paper", limit=1_000_000.0)
    yield


@pytest.fixture(autouse=True)
def clean_database():
    def _clear() -> None:
        session = SessionLocal()
        try:
            session.query(ExecutionModel).delete()
            session.query(OrderModel).delete()
            session.commit()
        finally:
            session.close()

    _clear()
    yield
    _clear()


def test_route_order_and_logging():
    client = TestClient(app)
    response = client.post(
        "/orders",
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
    assert response.status_code == 201
    order = response.json()
    assert order["order_id"].startswith("BN-")
    assert order["status"] in {"filled", "partially_filled"}

    log_resp = client.get("/orders/log")
    assert log_resp.status_code == 200
    log_payload = log_resp.json()
    assert log_payload["total"] == 1
    assert log_payload["limit"] == 100
    assert len(log_payload["items"]) == 1
    assert log_payload["items"][0]["broker"] == "binance"

    exec_resp = client.get("/executions")
    assert exec_resp.status_code == 200
    exec_payload = exec_resp.json()
    assert exec_payload["total"] >= 1
    assert exec_payload["items"]


def test_daily_notional_limit_enforced():
    client = TestClient(app)
    router.update_state(limit=30_000.0)

    response = client.post(
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
    assert response.status_code == 201

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


def test_risk_rule_rejection():
    client = TestClient(app)
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


def test_stop_loss_alert_and_endpoint():
    client = TestClient(app)
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


def test_preview_execution_plan():
    client = TestClient(app)
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
