from fastapi.testclient import TestClient

from fastapi.testclient import TestClient

from .utils import load_dashboard_app

load_dashboard_app()

from web_dashboard.app import data  # noqa: E402  pylint: disable=wrong-import-position
from web_dashboard.app.localization import build_translator  # noqa: E402  pylint: disable=wrong-import-position
from web_dashboard.app.schemas import DashboardContext, StrategyRuntimeStatus, StrategyStatus


def test_dashboard_template_includes_inplay_section(monkeypatch):
    app = load_dashboard_app()
    client = TestClient(app)

    response = client.get("/dashboard")
    assert response.status_code == 200
    html = response.text

    assert "Setups en temps réel" in html
    assert "inplay-setups-status" in html
    assert "Instantané statique" in html
    assert "Voir le rapport" in html
    assert "Rapports" in html
    assert "reports-center" in html


def test_dashboard_template_shows_clone_action(monkeypatch):
    context = DashboardContext(
        portfolios=[],
        transactions=[],
        alerts=[],
        metrics=None,
        reports=[],
        strategies=[
            StrategyStatus(
                id="clone-1",
                name="Stratégie clonée",
                status=StrategyRuntimeStatus.PENDING,
                enabled=False,
                strategy_type="orb",
                tags=[],
                last_error=None,
                last_execution=None,
                metadata={},
                derived_from="original-1",
                derived_from_name="Stratégie source",
            )
        ],
        logs=[],
        setups=None,
        data_sources={},
    )
    monkeypatch.setattr(data, "load_dashboard_context", lambda: context)

    client = TestClient(load_dashboard_app())
    response = client.get("/dashboard")

    assert response.status_code == 200
    html = response.text
    translator = build_translator("fr")
    assert "data-clone-endpoint" in html
    assert translator("Clone de {parent}", parent="Stratégie source")
    assert translator("Clone de {parent}", parent="Stratégie source")


def test_dashboard_template_uses_localization_bundle():
    client = TestClient(load_dashboard_app())
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert response.headers["content-language"] == "fr"
    html = response.text
    assert "id=\"i18n-bootstrap\"" in html
    assert "\"language\": \"fr\"" in html


def test_dashboard_template_resolves_language_from_query():
    client = TestClient(load_dashboard_app())
    response = client.get("/dashboard", params={"lang": "en"})

    assert response.status_code == 200
    assert response.headers["content-language"] == "en"
    html = response.text
    assert "Help &amp; training" in html
    assert "Dashboard" in html


def test_dashboard_template_resolves_language_from_header():
    client = TestClient(load_dashboard_app())
    response = client.get("/dashboard", headers={"accept-language": "en-US,en;q=0.8"})

    assert response.status_code == 200
    assert response.headers["content-language"] == "en"
    assert "Help &amp; training" in response.text


def test_dashboard_template_sets_language_cookie():
    client = TestClient(load_dashboard_app())
    response = client.get("/dashboard", params={"lang": "en"})

    assert response.status_code == 200
    assert response.cookies.get("dashboard_lang") == "en"


def test_dashboard_template_resolves_language_from_cookie():
    client = TestClient(load_dashboard_app())
    client.cookies.set("dashboard_lang", "en")

    response = client.get("/dashboard")

    assert response.status_code == 200
    assert response.headers["content-language"] == "en"
    assert "Help &amp; training" in response.text
