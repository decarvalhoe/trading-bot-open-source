import datetime as dt

import importlib

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response as HTTPXResponse

from .utils import load_dashboard_app


@pytest.fixture()
def dashboard_environment(monkeypatch):
    monkeypatch.setenv("WEB_DASHBOARD_AUTH_SERVICE_URL", "http://auth.local/")
    app = load_dashboard_app()
    module = importlib.import_module("web_dashboard.app.main")
    module.AUTH_SERVICE_BASE_URL = "http://auth.local/"
    return app, module


@pytest.fixture()
def client(dashboard_environment):
    app, _ = dashboard_environment
    return TestClient(app)


@pytest.fixture()
def dashboard_main(dashboard_environment):
    _, module = dashboard_environment
    return module


def _iso(dt_value):
    return dt_value.replace(tzinfo=dt.timezone.utc).isoformat().replace("+00:00", "Z")


@respx.mock
def test_account_login_success(client, dashboard_main):
    login_route = respx.post("http://auth.local/auth/login").mock(
        return_value=HTTPXResponse(200, json={"access_token": "access", "refresh_token": "refresh"})
    )
    me_route = respx.get("http://auth.local/auth/me").mock(
        return_value=HTTPXResponse(
            200,
            json={
                "id": 1,
                "email": "user@example.com",
                "roles": ["user"],
                "created_at": _iso(dt.datetime(2024, 5, 1, 12, 0)),
                "updated_at": _iso(dt.datetime(2024, 5, 1, 12, 30)),
            },
        )
    )

    response = client.post(
        "/account/login",
        json={"email": "user@example.com", "password": "secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["authenticated"] is True
    assert payload["user"]["email"] == "user@example.com"
    assert login_route.called
    assert me_route.called
    assert response.cookies.get(dashboard_main.ACCESS_TOKEN_COOKIE_NAME) == "access"
    assert response.cookies.get(dashboard_main.REFRESH_TOKEN_COOKIE_NAME) == "refresh"


@respx.mock
def test_account_login_failure_returns_error(client, dashboard_main):
    respx.post("http://auth.local/auth/login").mock(
        return_value=HTTPXResponse(401, json={"detail": "Invalid credentials"})
    )

    response = client.post(
        "/account/login",
        json={"email": "user@example.com", "password": "wrong"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"
    assert response.cookies.get(dashboard_main.ACCESS_TOKEN_COOKIE_NAME) is None


@respx.mock
def test_account_session_refreshes_tokens(client, dashboard_main):
    client.cookies.set(dashboard_main.ACCESS_TOKEN_COOKIE_NAME, "expired")
    client.cookies.set(dashboard_main.REFRESH_TOKEN_COOKIE_NAME, "refresh-old")

    me_first = respx.get("http://auth.local/auth/me").mock(
        side_effect=[
            HTTPXResponse(401, json={"detail": "Token expired"}),
            HTTPXResponse(
                200,
                json={
                    "id": 5,
                    "email": "refreshed@example.com",
                    "roles": ["user"],
                    "created_at": _iso(dt.datetime(2024, 5, 2, 8, 0)),
                    "updated_at": _iso(dt.datetime(2024, 5, 2, 8, 30)),
                },
            ),
        ]
    )
    respx.post("http://auth.local/auth/refresh").mock(
        return_value=HTTPXResponse(200, json={"access_token": "new-access", "refresh_token": "new-refresh"})
    )

    response = client.get("/account/session")

    assert response.status_code == 200
    payload = response.json()
    assert payload["authenticated"] is True
    assert payload["user"]["email"] == "refreshed@example.com"
    assert response.cookies.get(dashboard_main.ACCESS_TOKEN_COOKIE_NAME) == "new-access"
    assert response.cookies.get(dashboard_main.REFRESH_TOKEN_COOKIE_NAME) == "new-refresh"
    assert me_first.call_count == 2


@respx.mock
def test_account_session_handles_refresh_failure(client, dashboard_main):
    client.cookies.set(dashboard_main.ACCESS_TOKEN_COOKIE_NAME, "expired")
    client.cookies.set(dashboard_main.REFRESH_TOKEN_COOKIE_NAME, "refresh-old")

    respx.get("http://auth.local/auth/me").mock(return_value=HTTPXResponse(401, json={"detail": "Token expired"}))
    respx.post("http://auth.local/auth/refresh").mock(return_value=HTTPXResponse(401, json={"detail": "Invalid"}))

    response = client.get("/account/session")

    assert response.status_code == 200
    payload = response.json()
    assert payload["authenticated"] is False
    set_cookie_header = ",".join(response.headers.get_list("set-cookie"))
    assert dashboard_main.ACCESS_TOKEN_COOKIE_NAME in set_cookie_header
    assert "Max-Age=0" in set_cookie_header or "max-age=0" in set_cookie_header.lower()


@respx.mock
def test_account_logout_clears_cookies(client, dashboard_main):
    client.cookies.set(dashboard_main.ACCESS_TOKEN_COOKIE_NAME, "token")
    client.cookies.set(dashboard_main.REFRESH_TOKEN_COOKIE_NAME, "refresh")

    respx.post("http://auth.local/auth/logout").mock(return_value=HTTPXResponse(404))

    response = client.post("/account/logout")

    assert response.status_code == 200
    assert response.json()["authenticated"] is False
    set_cookie_header = ",".join(response.headers.get_list("set-cookie"))
    assert dashboard_main.ACCESS_TOKEN_COOKIE_NAME in set_cookie_header
    assert "Max-Age=0" in set_cookie_header or "max-age=0" in set_cookie_header.lower()

