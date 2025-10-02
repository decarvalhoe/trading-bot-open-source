import json
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from .utils import load_dashboard_app


@pytest.fixture()
def client(monkeypatch, tmp_path):
    storage_path = tmp_path / "tradingview-config.json"
    monkeypatch.setenv("WEB_DASHBOARD_TRADINGVIEW_STORAGE", str(storage_path))
    monkeypatch.setenv("WEB_DASHBOARD_TRADINGVIEW_LIBRARY_URL", "https://cdn.example.com/charting_library.js")
    monkeypatch.setenv("WEB_DASHBOARD_TRADINGVIEW_DEFAULT_SYMBOL", "BINANCE:ETHUSDT")
    monkeypatch.setenv("WEB_DASHBOARD_TRADINGVIEW_API_KEY", "demo-key")
    monkeypatch.setenv(
        "WEB_DASHBOARD_TRADINGVIEW_SYMBOL_MAP",
        json.dumps({"swing": "NASDAQ:AAPL", "__default__": "BINANCE:BTCUSDT"}),
    )
    dummy_markdown = types.ModuleType("markdown")
    dummy_markdown.markdown = lambda text, **_: text
    sys.modules.setdefault("markdown", dummy_markdown)
    dummy_python_multipart = types.ModuleType("python_multipart")
    dummy_python_multipart.__version__ = "0.0.13"
    sys.modules.setdefault("python_multipart", dummy_python_multipart)
    app = load_dashboard_app()
    test_client = TestClient(app)
    test_client.storage_path = storage_path
    return test_client


def test_tradingview_config_endpoint_returns_defaults(client):
    response = client.get("/config/tradingview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["api_key"] == "demo-key"
    assert payload["library_url"] == "https://cdn.example.com/charting_library.js"
    assert payload["default_symbol"] == "BINANCE:ETHUSDT"
    assert payload["symbol_map"]["swing"] == "NASDAQ:AAPL"


def test_tradingview_config_update_persists_overlays(client):
    response = client.put(
        "/config/tradingview",
        json={
            "overlays": [
                {
                    "id": "rsi-14",
                    "title": "RSI (14)",
                    "type": "indicator",
                    "settings": {"inputs": [14], "overlay": False},
                }
            ]
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert any(overlay["id"] == "rsi-14" for overlay in payload["overlays"])

    persisted = client.get("/config/tradingview")
    stored_payload = persisted.json()
    assert stored_payload["overlays"]
    assert stored_payload["overlays"][0]["title"] == "RSI (14)"

    storage_file = Path(getattr(client, "storage_path", ""))
    if storage_file.exists():
        raw_data = json.loads(storage_file.read_text("utf-8"))
        assert raw_data["overlays"][0]["id"] == "rsi-14"
