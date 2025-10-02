from __future__ import annotations

from fastapi.testclient import TestClient

from .utils import load_dashboard_app


def test_help_center_page_renders():
    app = load_dashboard_app()
    client = TestClient(app)

    response = client.get("/help")
    assert response.status_code == 200
    html = response.text

    assert "Aide &amp; formation" in html
    assert "Suivi de progression" in html
    assert "FAQ opérationnelle" in html
    assert "role=\"progressbar\"" in html
    assert "data-articles-endpoint" in html


def test_help_articles_api_returns_articles_and_progress():
    app = load_dashboard_app()
    client = TestClient(app)

    response = client.get("/help/articles")
    assert response.status_code == 200
    payload = response.json()

    assert "articles" in payload and payload["articles"], "Aucun article renvoyé"
    assert "progress" in payload
    base_progress = payload["progress"]
    assert base_progress["total_resources"] >= len(payload["articles"])

    slug = payload["articles"][0]["slug"]
    follow_up = client.get(f"/help/articles?viewed={slug}")
    assert follow_up.status_code == 200
    updated = follow_up.json()["progress"]
    assert updated["completed_resources"] >= base_progress["completed_resources"]


def test_navigation_includes_help_link():
    app = load_dashboard_app()
    client = TestClient(app)

    response = client.get("/help")
    assert response.status_code == 200
    html = response.text

    assert "Aide &amp; formation" in html
    assert "/help" in html
