from fastapi.testclient import TestClient

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
