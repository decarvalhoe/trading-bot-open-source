"""Tests covering the account creation flow exposed by the dashboard."""

import importlib

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response as HTTPXResponse

from .utils import load_dashboard_app


@pytest.fixture()
def client(monkeypatch):
    load_dashboard_app.cache_clear()
    monkeypatch.setenv("AUTH_BASE_URL", "http://auth.local/")
    monkeypatch.setenv("WEB_DASHBOARD_AUTH_SERVICE_URL", "http://auth.local/")
    app = load_dashboard_app()
    module = importlib.import_module("web_dashboard.app.main")
    module.AUTH_PUBLIC_BASE_URL = "http://auth.local/"
    module.AUTH_SERVICE_BASE_URL = "http://auth.local/"
    test_client = TestClient(app)
    yield test_client
    load_dashboard_app.cache_clear()


def test_register_page_displays_form(client):
    response = client.get("/account/register", headers={"accept-language": "fr-FR,fr;q=0.9"})

    assert response.status_code == 200
    assert response.headers.get("Content-Language") == "fr"

    html = response.text
    form_action = f"{client.base_url}/account/register"
    assert f'<form class="form-grid" action="{form_action}" method="post">' in html
    assert '<input type="email" name="email" autocomplete="email"' in html
    assert '<input type="password" name="password" autocomplete="new-password"' in html
    assert "Créer mon compte" in html
    assert "Se connecter" in html


@respx.mock
def test_register_success_redirects_to_login(client):
    register_route = respx.post("http://auth.local/auth/register").mock(
        return_value=HTTPXResponse(201, json={"id": 1})
    )

    response = client.post(
        "/account/register",
        data={"email": "new.user@example.com", "password": "StrongPwd42!"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/account/login?created=1")
    assert register_route.called


@respx.mock
def test_register_failure_renders_error_message(client):
    respx.post("http://auth.local/auth/register").mock(
        return_value=HTTPXResponse(400, json={"detail": "Mot de passe trop court"})
    )

    response = client.post(
        "/account/register",
        data={"email": "new.user@example.com", "password": "weak"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    html = response.text
    assert "Mot de passe trop court" in html
    assert 'value="new.user@example.com"' in html
