from fastapi.testclient import TestClient

from web_dashboard.app import data
from web_dashboard.app.schemas import DashboardContext, StrategyRuntimeStatus, StrategyStatus

from .utils import load_dashboard_app


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
    assert "Clone de Stratégie source" in html
    assert "strategy-actions__form" in html
    assert ">Cloner<" in html
