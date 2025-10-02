import sys

import respx
from fastapi.testclient import TestClient
from httpx import Response

from .utils import load_dashboard_app


def _load_main_module():
    load_dashboard_app()
    return sys.modules["web_dashboard.app.main"]


@respx.mock
def test_generate_strategy_proxies_to_ai_service(monkeypatch):
    main_module = _load_main_module()
    monkeypatch.setattr(main_module, "AI_ASSISTANT_BASE_URL", "http://assistant.local/")
    route = respx.post("http://assistant.local/generate").mock(
        return_value=Response(
            200,
            json={
                "draft": {
                    "summary": "Breakout IA",
                    "yaml_strategy": "name: ai-breakout",
                    "python_strategy": None,
                    "indicators": ["RSI"],
                    "warnings": ["Vérifier la liquidité"],
                    "metadata": {"suggested_name": "AI Breakout"},
                },
                "request": {
                    "prompt": "Breakout sur BTC",
                    "preferred_format": "yaml",
                    "indicators": ["RSI"],
                    "risk_profile": None,
                    "timeframe": None,
                    "capital": None,
                    "notes": None,
                },
            },
        )
    )

    client = TestClient(load_dashboard_app())
    payload = {"prompt": "Breakout sur BTC", "preferred_format": "yaml"}
    response = client.post("/strategies/generate", json=payload)

    assert response.status_code == 200
    assert route.called
    body = response.json()
    assert body["draft"]["summary"] == "Breakout IA"
    assert body["draft"].get("yaml") == "name: ai-breakout"
    assert body["draft"]["python"] is None
    assert body["draft"]["indicators"] == ["RSI"]


@respx.mock
def test_import_assistant_strategy_proxies_to_algo_engine(monkeypatch):
    main_module = _load_main_module()
    monkeypatch.setattr(main_module, "ALGO_ENGINE_BASE_URL", "http://algo.local/")
    route = respx.post("http://algo.local/strategies/import").mock(
        return_value=Response(
            201,
            json={
                "id": "strat-123",
                "name": "AI Breakout",
                "source_format": "yaml",
                "tags": ["ai"],
            },
        )
    )

    client = TestClient(load_dashboard_app())
    payload = {
        "format": "yaml",
        "content": "name: ai-breakout",
        "tags": ["ai"],
        "enabled": True,
    }
    response = client.post("/strategies/import/assistant", json=payload)

    assert response.status_code == 200
    assert route.called
    assert response.json()["id"] == "strat-123"
