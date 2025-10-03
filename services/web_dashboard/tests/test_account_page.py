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

    # The template should expose the correct lang attribute and account mount point.
    assert "<html lang=\"fr\"" in html
    assert '<div' in html and 'id="account-app"' in html
    assert 'data-session-endpoint="' in html and "/account/session" in html
    assert 'data-login-endpoint="' in html and "/account/login" in html
    assert 'data-logout-endpoint="' in html and "/account/logout" in html

    # The hydration placeholder should encourage enabling JavaScript.
    assert "Activez JavaScript pour gérer votre session" in html

    # The React bundle is loaded as an ES module.
    assert '<script type="module" src="/static/dist/account-app.js"></script>' in html
