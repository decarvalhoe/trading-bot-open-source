"""Tests validating the service status page."""

import importlib

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response as HTTPXResponse

from .utils import load_dashboard_app


@pytest.fixture()
def client(monkeypatch):
    load_dashboard_app.cache_clear()
    monkeypatch.setenv("WEB_DASHBOARD_AUTH_PUBLIC_URL", "http://auth.local/")
    monkeypatch.setenv("WEB_DASHBOARD_AUTH_SERVICE_URL", "http://auth.local/")
    monkeypatch.setenv("WEB_DASHBOARD_REPORTS_BASE_URL", "http://reports.local/")
    monkeypatch.setenv("WEB_DASHBOARD_ALGO_ENGINE_URL", "http://algo.local/")
    monkeypatch.setenv("WEB_DASHBOARD_ORDER_ROUTER_BASE_URL", "http://router.local/")
    monkeypatch.setenv("WEB_DASHBOARD_MARKETPLACE_URL", "http://market.local/")
    app = load_dashboard_app()
    module = importlib.import_module("web_dashboard.app.main")
    module.AUTH_PUBLIC_BASE_URL = "http://auth.local/"
    module.AUTH_SERVICE_BASE_URL = "http://auth.local/"
    module.REPORTS_BASE_URL = "http://reports.local/"
    module.ALGO_ENGINE_BASE_URL = "http://algo.local/"
    module.ORDER_ROUTER_BASE_URL = "http://router.local/"
    module.MARKETPLACE_BASE_URL = "http://market.local/"
    test_client = TestClient(app)
    yield test_client
    load_dashboard_app.cache_clear()


@respx.mock
def test_status_page_displays_all_services(client):
    respx.get("http://auth.local/health").mock(return_value=HTTPXResponse(200, json={"status": "ok"}))
    respx.get("http://reports.local/health").mock(return_value=HTTPXResponse(200, json={"status": "healthy"}))
    respx.get("http://algo.local/health").mock(return_value=HTTPXResponse(200, json={"status": "up"}))
    respx.get("http://router.local/health").mock(return_value=HTTPXResponse(200, json={"status": "ok"}))
    respx.get("http://market.local/health").mock(return_value=HTTPXResponse(200, json={"status": "up"}))

    response = client.get("/status", headers={"accept-language": "fr-FR,fr;q=0.9"})

    assert response.status_code == 200
    assert response.headers.get("Content-Language") == "fr"
    html = response.text
    assert "Service d&#39;authentification" in html
    assert "Service de rapports" in html
    assert html.count("badge--success") >= 5


@respx.mock
def test_status_page_marks_failures(client):
    respx.get("http://auth.local/health").mock(return_value=HTTPXResponse(200, json={"status": "ok"}))
    respx.get("http://reports.local/health").mock(return_value=HTTPXResponse(503))
    respx.get("http://algo.local/health").mock(return_value=HTTPXResponse(500, json={"status": "down"}))
    respx.get("http://router.local/health").mock(return_value=HTTPXResponse(200, json={"status": "ok"}))
    respx.get("http://market.local/health").mock(return_value=HTTPXResponse(200, json={"status": "ok"}))

    response = client.get("/status")

    assert response.status_code == 200
    html = response.text
    assert "HTTP 503" in html
    assert "Indisponible" in html
    assert "badge--critical" in html
