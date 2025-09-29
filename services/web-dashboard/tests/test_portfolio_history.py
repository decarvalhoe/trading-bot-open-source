from fastapi.testclient import TestClient

from .utils import load_dashboard_app


client = TestClient(load_dashboard_app())


def test_portfolio_history_endpoint_returns_series():
    response = client.get("/portfolios/history")
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert isinstance(payload["items"], list)
    assert payload["items"], "history payload should not be empty"
    first = payload["items"][0]
    assert "series" in first
    assert isinstance(first["series"], list)
    assert first["series"], "series should contain at least one observation"
    point = first["series"][0]
    assert "timestamp" in point and "value" in point
