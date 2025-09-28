from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from services.streaming.app.config import get_settings
from services.streaming.app.main import create_app


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("STREAMING_SERVICE_TOKEN_REPORTS", "reports-token")
    monkeypatch.setenv("STREAMING_SERVICE_TOKEN_INPLAY", "inplay-token")
    monkeypatch.setenv("ENTITLEMENTS_BYPASS", "1")
    from libs.entitlements.fastapi import Entitlements, EntitlementsClient

    async def _fake_require(self, customer_id, capabilities=None, quotas=None):  # type: ignore[unused-argument]
        return Entitlements(customer_id=customer_id, features={cap: True for cap in capabilities or []}, quotas={})

    monkeypatch.setattr(EntitlementsClient, "require", _fake_require, raising=False)
    # Reset settings cache to ensure env vars are picked up
    get_settings.cache_clear()  # type: ignore[attr-defined]
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def _auth_headers(customer: str) -> dict[str, str]:
    return {"x-customer-id": customer}


def test_websocket_broadcasts_ingested_event(client: TestClient):
    client.post(
        "/rooms",
        headers=_auth_headers("customer-1"),
        json={
            "room_id": "public-room",
            "title": "Scalping live",
        },
    )
    with client.websocket_connect(
        "/ws/rooms/public-room",
        headers={"x-customer-id": "viewer-1"},
    ) as websocket:
        response = client.post(
            "/ingest/reports",
            headers={"x-service-token": "reports-token"},
            json={
                "room_id": "public-room",
                "source": "reports",
                "payload": {"indicator": "rsi", "value": 42},
            },
        )
        assert response.status_code == 202
        message = websocket.receive_json()
        assert message["payload"] == {"indicator": "rsi", "value": 42}
        assert message["source"] == "reports"


def test_session_lifecycle_events_are_streamed(client: TestClient):
    client.post(
        "/rooms",
        headers=_auth_headers("customer-1"),
        json={
            "room_id": "swing-room",
            "title": "Swing trading",
        },
    )
    schedule = client.post(
        "/sessions",
        headers=_auth_headers("customer-1"),
        json={
            "room_id": "swing-room",
            "title": "Morning setup",
            "host_id": "coach-1",
            "scheduled_for": datetime.now(tz=timezone.utc).isoformat(),
        },
    )
    session_id = schedule.json()["session_id"]

    with client.websocket_connect(
        "/ws/rooms/swing-room",
        headers={"x-customer-id": "viewer-2"},
    ) as websocket:
        start_resp = client.post(
            f"/sessions/{session_id}/start",
            headers=_auth_headers("customer-1"),
        )
        assert start_resp.status_code == 200
        message = websocket.receive_json()
        assert message["payload"]["type"] == "session_started"
        assert message["payload"]["session_id"] == session_id
