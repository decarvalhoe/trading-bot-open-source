import sys
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from libs.alert_events import AlertEventRepository
from libs.alert_events.models import AlertEventBase

from .utils import load_dashboard_app


@pytest.fixture()
def dashboard_history_module(monkeypatch, tmp_path):
    db_path = tmp_path / "alerts_history.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("WEB_DASHBOARD_ALERT_EVENTS_DATABASE_URL", db_url)
    load_dashboard_app.cache_clear()
    app = load_dashboard_app()
    module = sys.modules["web_dashboard.app.main"]
    # Ensure tables are created for the dedicated test database
    AlertEventBase.metadata.create_all(bind=module._alert_events_engine)
    module.app.dependency_overrides.clear()
    yield module
    module.app.dependency_overrides.clear()
    load_dashboard_app.cache_clear()


def seed_events(module, count=5):
    session = module._alert_events_session_factory()
    repository = AlertEventRepository()
    base_time = datetime.utcnow()
    try:
        for index in range(count):
            repository.record_event(
                session,
                trigger_id=100 + index,
                rule_id=200 + index,
                rule_name=f"Rule {index}",
                strategy=f"Strategy {index % 2}",
                severity="critical" if index % 2 == 0 else "warning",
                symbol="BTC" if index % 2 == 0 else "ETH",
                triggered_at=base_time - timedelta(minutes=index),
                context={"index": index},
                delivery_status="received",
            )
    finally:
        session.close()


def test_alert_history_pagination(dashboard_history_module):
    seed_events(dashboard_history_module, count=5)
    client = TestClient(dashboard_history_module.app)

    response = client.get("/alerts/history", params={"page": 1, "page_size": 2})
    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["page"] == 1
    assert payload["pagination"]["page_size"] == 2
    assert payload["pagination"]["total"] == 5
    assert len(payload["items"]) == 2
    first_event = payload["items"][0]
    assert first_event["rule_name"] == "Rule 0"
    assert "triggered_at" in first_event

    response = client.get(
        "/alerts/history",
        params={"page": 2, "page_size": 2, "severity": "warning", "strategy": "Strategy 1"},
    )
    assert response.status_code == 200
    filtered = response.json()
    assert filtered["pagination"]["page"] == 2
    assert filtered["pagination"]["total"] == 2
    assert all(item["severity"] == "warning" for item in filtered["items"])
    assert all(item["strategy"] == "Strategy 1" for item in filtered["items"])
