from fastapi.testclient import TestClient

from services.auth_service.app.main import app


def test_health_endpoint_is_available() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "auth_service"}
