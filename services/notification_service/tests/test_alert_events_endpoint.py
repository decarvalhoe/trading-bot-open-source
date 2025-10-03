import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))


@pytest.fixture()
def notification_app(monkeypatch, tmp_path):
    db_url = f"sqlite:///{tmp_path / 'alerts_history.db'}"
    monkeypatch.setenv("NOTIFICATION_SERVICE_EVENTS_DATABASE_URL", db_url)
    monkeypatch.delenv("ALERT_EVENTS_DATABASE_URL", raising=False)

    module = importlib.import_module("app.main")
    module = importlib.reload(module)
    yield module.app, module


def test_register_alert_event_creates_and_updates(notification_app):
    app, module = notification_app
    client = TestClient(app)

    payload = {
        "event_id": None,
        "trigger_id": 42,
        "rule_id": 7,
        "rule_name": "Momentum breakout",
        "strategy": "Momentum",
        "severity": "critical",
        "symbol": "BTC",
        "triggered_at": "2024-04-02T12:00:00Z",
        "context": {"price": 42000},
    }

    response = client.post("/notifications/alerts", json=payload)
    assert response.status_code == 202
    first_event = response.json()
    assert first_event["status"] == "recorded"
    assert first_event["event_id"]

    update_payload = {
        **payload,
        "event_id": first_event["event_id"],
        "severity": "warning",
        "notification_channel": "email",
        "notification_target": "ops@example.com",
    }

    response = client.post("/notifications/alerts", json=update_payload)
    assert response.status_code == 202
    updated = response.json()
    assert updated["event_id"] == first_event["event_id"]

    session = module.EventsSessionLocal()
    try:
        event = module._alert_events_repository.get_by_id(session, updated["event_id"])
        assert event is not None
        assert event.severity == "warning"
        assert event.notification_channel == "email"
        assert event.notification_target == "ops@example.com"
        assert event.delivery_status == "received"
    finally:
        session.close()
