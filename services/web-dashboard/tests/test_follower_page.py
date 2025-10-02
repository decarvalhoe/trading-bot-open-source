from __future__ import annotations

from fastapi.testclient import TestClient

from web_dashboard.app import data
from web_dashboard.app.schemas import FollowerCopySnapshot, FollowerDashboardContext

from .utils import load_dashboard_app


def test_follower_dashboard_renders_table(monkeypatch) -> None:
    context = FollowerDashboardContext(
        copies=[
            FollowerCopySnapshot(
                listing_id=1,
                strategy_name="Momentum Edge",
                leader_id="creator-1",
                leverage=1.2,
                allocated_capital=1000.0,
                divergence_bps=42.0,
                estimated_fees=5.0,
                replication_status="filled",
            )
        ],
        viewer_id="investor-1",
    )
    load_dashboard_app.cache_clear()
    app = load_dashboard_app()
    from web_dashboard.app import main as dashboard_main

    monkeypatch.setattr(data, "load_follower_dashboard", lambda viewer_id: context)
    monkeypatch.setattr(dashboard_main, "load_follower_dashboard", lambda viewer_id: context)
    client = TestClient(app)
    response = client.get("/dashboard/followers")
    assert response.status_code == 200
    html = response.text
    assert "Suivi des copies" in html
    assert "Momentum Edge" in html
    assert "creator-1" in html
    assert "1.20" in html


def test_follower_dashboard_uses_fallback_message(monkeypatch) -> None:
    context = FollowerDashboardContext(
        copies=[],
        viewer_id="investor-9",
        source="fallback",
        fallback_reason="Marketplace indisponible",
    )
    load_dashboard_app.cache_clear()
    app = load_dashboard_app()
    from web_dashboard.app import main as dashboard_main

    monkeypatch.setattr(data, "load_follower_dashboard", lambda viewer_id: context)
    monkeypatch.setattr(dashboard_main, "load_follower_dashboard", lambda viewer_id: context)
    client = TestClient(app)
    response = client.get("/dashboard/followers")
    assert response.status_code == 200
    assert "Marketplace indisponible" in response.text
