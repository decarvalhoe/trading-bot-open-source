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
    metadata = log_payload["metadata"]
    assert metadata["total"] == 1
    assert metadata["limit"] == 100
    assert metadata["offset"] == 0
    assert len(log_payload["items"]) == 1
    assert log_payload["items"][0]["broker"] == "binance"

    exec_resp = client.get("/executions")
    assert exec_resp.status_code == 200
    exec_payload = exec_resp.json()
    exec_metadata = exec_payload["metadata"]
    assert exec_metadata["total"] >= 1
    assert exec_metadata["limit"] == 100
    assert exec_metadata["offset"] == 0
    assert exec_payload["items"]


def test_orders_log_filters_by_account():
    client = TestClient(app)
    first = client.post(
        "/orders",
        json={
            "broker": "binance",
            "venue": "binance.spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "limit",
            "quantity": 0.5,
            "price": 30_000,
            "account_id": "acct-1",
        },
    )
    assert first.status_code == 201

    second = client.post(
        "/orders",
        json={
            "broker": "binance",
            "venue": "binance.spot",
            "symbol": "ETHUSDT",
            "side": "buy",
            "order_type": "limit",
            "quantity": 1.0,
            "price": 2_000,
            "account_id": "acct-2",
        },
    )
    assert second.status_code == 201

    response = client.get("/orders/log", params={"account_id": "acct-1"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["total"] == 1
    assert all(order["account_id"] == "acct-1" for order in payload["items"])


def test_executions_filters_by_symbol_and_account():
    client = TestClient(app)
    first = client.post(
        "/orders",
        json={
            "broker": "binance",
            "venue": "binance.spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "limit",
            "quantity": 0.5,
            "price": 30_000,
            "account_id": "acct-1",
        },
    )
    assert first.status_code == 201

    second = client.post(
        "/orders",
        json={
            "broker": "binance",
            "venue": "binance.spot",
            "symbol": "ETHUSDT",
            "side": "buy",
            "order_type": "limit",
            "quantity": 1.0,
            "price": 2_000,
            "account_id": "acct-2",
        },
    )
    assert second.status_code == 201

    response = client.get(
        "/executions", params={"symbol": "ETHUSDT", "account_id": "acct-2"}
    )
    assert response.status_code == 200
    payload = response.json()
    metadata = payload["metadata"]
    assert metadata["total"] >= 1
    assert metadata["symbol"] == "ETHUSDT"
    assert metadata["account_id"] == "acct-2"
    assert all(exec_["symbol"] == "ETHUSDT" for exec_ in payload["items"])
    assert all(exec_["account_id"] == "acct-2" for exec_ in payload["items"])


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
