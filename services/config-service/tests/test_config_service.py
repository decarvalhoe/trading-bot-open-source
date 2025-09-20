import importlib.util
import os
from pathlib import Path

from fastapi.testclient import TestClient

_service_root = Path(__file__).resolve().parents[1]
_main_path = _service_root / "app" / "main.py"
_spec = importlib.util.spec_from_file_location("config_service_main", _main_path)
_module = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_module)  # type: ignore[arg-type]
app = _module.app  # type: ignore[attr-defined]

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_current_config():
    response = client.get("/config/current")
    assert response.status_code == 200
    data = response.json()
    assert data["APP_NAME"] == "trading-bot-config"


def test_update_config(tmp_path):
    os.environ["ENVIRONMENT"] = "test"
    os.environ["CONFIG_DATA_DIR"] = str(tmp_path)

    update_payload = {"APP_NAME": "My-Awesome-Trading-Bot"}
    response = client.post("/config/update", json=update_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["APP_NAME"] == "My-Awesome-Trading-Bot"
    assert data["ENVIRONMENT"] == "test"

    test_config_path = tmp_path / "config.test.json"
    assert test_config_path.exists()
    assert "My-Awesome-Trading-Bot" in test_config_path.read_text(encoding="utf-8")

    del os.environ["ENVIRONMENT"]
    del os.environ["CONFIG_DATA_DIR"]
