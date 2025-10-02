import io

import pytest
from httpx import Response
from fastapi.testclient import TestClient

from .utils import load_dashboard_app


respx = pytest.importorskip("respx")


def _load_main_module():
    load_dashboard_app()
    return __import__("web_dashboard.app.main", fromlist=["app"])


@respx.mock
def test_upload_strategy_file_proxies_to_algo_engine(monkeypatch):
    main_module = _load_main_module()
    monkeypatch.setattr(main_module, "ALGO_ENGINE_BASE_URL", "http://algo.local/")
    route = respx.post("http://algo.local/strategies/import").mock(
        return_value=Response(200, json={"id": "uploaded", "status": "ok"})
    )

    client = TestClient(load_dashboard_app())
    payload = "name: Importée\nrules:\n  - when: {}\n    signal:\n      steps: []\n"
    files = {"file": ("import.yaml", payload, "application/x-yaml")}
    data = {"name": "Importée"}

    response = client.post("/strategies/import/upload", files=files, data=data)

    assert response.status_code == 200
    assert route.called
    body = route.calls.last.request.json()
    assert body["name"] == "Importée"
    assert body["format"] == "yaml"
    assert "rules" in body["content"]


def test_render_strategies_includes_presets():
    client = TestClient(load_dashboard_app())
    response = client.get("/strategies")

    assert response.status_code == 200
    html = response.text
    assert "data-presets=" in html
    assert "Importer un fichier" in html
    assert "Modèles disponibles" in html
