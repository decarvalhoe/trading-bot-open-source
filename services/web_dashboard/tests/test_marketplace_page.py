import sys
import types

from fastapi.testclient import TestClient

from .utils import load_dashboard_app


def test_marketplace_template_contains_mount_point(monkeypatch):
    monkeypatch.setitem(sys.modules, "markdown", types.ModuleType("markdown"))
    multipart_stub = types.ModuleType("python_multipart")
    multipart_stub.__version__ = "0.0.16"
    monkeypatch.setitem(sys.modules, "python_multipart", multipart_stub)
    app = load_dashboard_app()
    client = TestClient(app)

    response = client.get("/marketplace")
    assert response.status_code == 200
    html = response.text

    assert "marketplace-root" in html
    assert "data-endpoint=\"/marketplace/listings\"" in html
    assert "Marketplace de stratégies" in html
