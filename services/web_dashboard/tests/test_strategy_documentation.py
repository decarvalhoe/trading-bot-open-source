from fastapi.testclient import TestClient

from .utils import load_dashboard_app


def test_strategy_documentation_page_renders():
    app = load_dashboard_app()
    client = TestClient(app)
    from web_dashboard.app.documentation import load_strategy_documentation

    response = client.get("/strategies/documentation")
    assert response.status_code == 200
    html = response.text

    docs = load_strategy_documentation()
    assert docs.schema_version in html
    assert "Documentation stratégies" in html
    assert "docs/strategies/README.md" in html


def test_navigation_includes_documentation_link():
    app = load_dashboard_app()
    client = TestClient(app)
    _ = load_dashboard_app()

    response = client.get("/dashboard")
    assert response.status_code == 200
    html = response.text

    assert "Documentation stratégies" in html
    assert "/strategies/documentation" in html
