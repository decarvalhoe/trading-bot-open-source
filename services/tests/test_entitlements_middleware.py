from fastapi import FastAPI
from fastapi.testclient import TestClient

from libs.entitlements.fastapi import install_entitlements_middleware


def test_health_endpoint_does_not_require_entitlements(monkeypatch):
    calls = []

    class DummyClient:
        async def require(self, *args, **kwargs):  # pragma: no cover - should not be called
            calls.append((args, kwargs))
            raise AssertionError("entitlements client should not be invoked")

    monkeypatch.setattr(
        "libs.entitlements.fastapi.EntitlementsClient",
        lambda *args, **kwargs: DummyClient(),
    )

    app = FastAPI()
    install_entitlements_middleware(app)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert not calls
