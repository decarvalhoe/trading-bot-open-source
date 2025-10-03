"""Tests for the account management page of the dashboard."""

from fastapi.testclient import TestClient

from .utils import load_dashboard_app


def test_account_page_exposes_login_and_api_forms():
    """The /account page should render the login and API key management forms."""

    app = load_dashboard_app()
    client = TestClient(app)

    response = client.get("/account", headers={"accept-language": "fr-FR,fr;q=0.9"})

    assert response.status_code == 200
    assert response.headers.get("Content-Language") == "fr"

    html = response.text

    # The template should expose the correct lang attribute and login form inputs.
    assert "<html lang=\"fr\"" in html
    login_url = f"{client.base_url}/account/login"
    assert f'data-login-endpoint="{login_url}"' in html
    assert f'<form class="form-grid" action="{login_url}" method="post">' in html
    assert '<input type="email" name="email" autocomplete="email" required />' in html
    assert '<input type="password" name="password" autocomplete="current-password" required />' in html

    # The API key management form and its inputs must also be present.
    assert '<form class="form-grid" action="#" method="post">' in html
    assert '<select name="exchange" required>' in html
    assert '<input type="text" name="public" autocomplete="off" required />' in html
    assert '<input type="password" name="secret" autocomplete="off" required />' in html
