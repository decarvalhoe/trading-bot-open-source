import json
import pytest
from fastapi.testclient import TestClient
from httpx import Response

from .utils import load_dashboard_app

respx = pytest.importorskip("respx")


def _load_main_module():
    load_dashboard_app()
    return __import__("web_dashboard.app.main", fromlist=["app"])


@respx.mock
def test_save_strategy_structured_payload(monkeypatch):
    main_module = _load_main_module()
    monkeypatch.setattr(main_module, "ALGO_ENGINE_BASE_URL", "http://algo.local/")
    route = respx.post("http://algo.local/strategies").mock(
        return_value=Response(201, json={"id": "strat-1", "status": "created"})
    )
    client = TestClient(load_dashboard_app())
    payload = {
        "name": "Stratégie rapide",
        "strategy_type": "declarative",
        "parameters": {"definition": {"rules": []}},
        "metadata": {"symbol": "BTCUSDT"},
        "enabled": False,
        "tags": ["one-click"],
    }

    response = client.post("/strategies/save", json=payload)

    assert response.status_code == 200
    assert route.called
    forwarded = json.loads(route.calls.last.request.content)
    assert forwarded["name"] == "Stratégie rapide"
    assert forwarded["strategy_type"] == "declarative"
    assert forwarded["metadata"]["symbol"] == "BTCUSDT"


@respx.mock
def test_backtest_run_proxy_and_detail(monkeypatch):
    main_module = _load_main_module()
    monkeypatch.setattr(main_module, "ALGO_ENGINE_BASE_URL", "http://algo.local/")

    run_route = respx.post("http://algo.local/backtests").mock(
        return_value=Response(
            201,
            json={
                "id": 42,
                "strategy_id": "strat-1",
                "equity_curve": [1000, 1010],
                "profit_loss": 10,
                "artifacts": [],
            },
        )
    )
    detail_route = respx.get("http://algo.local/backtests/42").mock(
        return_value=Response(
            200,
            json={"id": 42, "strategy_id": "strat-1", "artifacts": []},
        )
    )

    client = TestClient(load_dashboard_app())
    run_payload = {
        "strategy_id": "strat-1",
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "lookback_days": 30,
        "initial_balance": 10_000,
        "metadata": {"fast_length": 5, "slow_length": 20},
    }

    response = client.post("/backtests/run", json=run_payload)
    assert response.status_code == 200
    assert run_route.called
    forwarded = json.loads(run_route.calls.last.request.content)
    assert forwarded["strategy_id"] == "strat-1"
    assert forwarded["metadata"]["symbol"] == "BTCUSDT"
    assert isinstance(forwarded.get("market_data"), list)

    detail_response = client.get("/backtests/42")
    assert detail_response.status_code == 200
    assert detail_route.called


def test_render_one_click_page_contains_root():
    client = TestClient(load_dashboard_app())
    response = client.get("/strategies/new")
    assert response.status_code == 200
    assert "strategy-one-click-root" in response.text
