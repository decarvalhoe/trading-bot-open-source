from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

import pytest
from fastapi.testclient import TestClient

from .utils import load_dashboard_app


@dataclass
class DummyAlertsClient:
    created: List[Dict[str, Any]] = field(default_factory=list)
    updated: List[Tuple[str, Dict[str, Any]]] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)

    def create_alert(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.created.append(dict(payload))
        return {
            "id": payload.get("id", "generated-alert"),
            "title": payload["title"],
            "detail": payload["detail"],
            "risk": payload.get("risk", "info"),
            "acknowledged": payload.get("acknowledged", False),
            "created_at": payload.get("created_at", "2024-04-02T12:00:00Z"),
        }

    def update_alert(self, alert_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.updated.append((alert_id, dict(payload)))
        base = {
            "id": alert_id,
            "title": payload.get("title", "Existing alert"),
            "detail": payload.get("detail", "Detail"),
            "risk": payload.get("risk", "info"),
            "acknowledged": payload.get("acknowledged", False),
            "created_at": payload.get("created_at", "2024-04-02T12:00:00Z"),
        }
        return base

    def delete_alert(self, alert_id: str) -> None:
        self.deleted.append(alert_id)


@pytest.fixture()
def dashboard_module(monkeypatch):
    """Expose the dashboard FastAPI module with clean dependency overrides."""

    load_dashboard_app()
    module = importlib.import_module("web_dashboard.app.main")
    module.app.dependency_overrides.clear()
    yield module
    module.app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(monkeypatch):
    monkeypatch.setenv("WEB_DASHBOARD_ALERTS_TOKEN", "secret-token")
    return {"Authorization": "Bearer secret-token"}


def test_create_alert_delegates_to_engine(dashboard_module, auth_headers):
    dummy = DummyAlertsClient()
    dashboard_module.app.dependency_overrides[dashboard_module.get_alerts_client] = lambda: dummy
    client = TestClient(dashboard_module.app)

    response = client.post(
        "/alerts",
        json={
            "title": "Nouvelle alerte",
            "detail": "Supervision de la marge",
            "risk": "critical",
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["title"] == "Nouvelle alerte"
    assert payload["risk"] == "critical"
    assert dummy.created and dummy.created[0]["title"] == "Nouvelle alerte"


def test_update_alert_returns_payload_from_engine(dashboard_module, auth_headers):
    dummy = DummyAlertsClient()
    dashboard_module.app.dependency_overrides[dashboard_module.get_alerts_client] = lambda: dummy
    client = TestClient(dashboard_module.app)

    response = client.put(
        "/alerts/alert-1",
        json={"detail": "Mise à jour effectuée", "acknowledged": True},
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "alert-1"
    assert payload["detail"] == "Mise à jour effectuée"
    assert payload["acknowledged"] is True
    assert dummy.updated == [("alert-1", {"detail": "Mise à jour effectuée", "acknowledged": True})]


def test_delete_alert_requires_engine_call(dashboard_module, auth_headers):
    dummy = DummyAlertsClient()
    dashboard_module.app.dependency_overrides[dashboard_module.get_alerts_client] = lambda: dummy
    client = TestClient(dashboard_module.app)

    response = client.delete("/alerts/alert-2", headers=auth_headers)

    assert response.status_code == 204
    assert dummy.deleted == ["alert-2"]


def test_alert_routes_require_auth_when_token_configured(dashboard_module, auth_headers):
    dummy = DummyAlertsClient()
    dashboard_module.app.dependency_overrides[dashboard_module.get_alerts_client] = lambda: dummy
    client = TestClient(dashboard_module.app)

    response = client.post(
        "/alerts",
        json={"title": "Non autorisé", "detail": "Test"},
    )
    assert response.status_code == 401

    invalid = client.post(
        "/alerts",
        json={"title": "Mauvais jeton", "detail": "Test"},
        headers={"Authorization": "Bearer autre-chose"},
    )
    assert invalid.status_code == 403
