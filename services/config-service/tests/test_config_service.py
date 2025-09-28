import importlib
import importlib.util
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

_service_root = Path(__file__).resolve().parents[1]
_package_name = "config_service_app"

if str(_service_root.parents[1]) not in sys.path:
    sys.path.append(str(_service_root.parents[1]))

if _package_name not in sys.modules:
    _package_spec = importlib.util.spec_from_file_location(
        _package_name,
        _service_root / "app" / "__init__.py",
        submodule_search_locations=[str(_service_root / "app")],
    )
    assert _package_spec and _package_spec.loader
    _package_module = importlib.util.module_from_spec(_package_spec)
    sys.modules[_package_name] = _package_module
    _package_spec.loader.exec_module(_package_module)  # type: ignore[arg-type]

main = importlib.import_module(f"{_package_name}.main")
_persistence = importlib.import_module(f"{_package_name}.persistence")
app = main.app  # type: ignore[attr-defined]

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
    _persistence.CONFIG_FILES["test"] = os.path.join(str(tmp_path), "config.test.json")

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


def test_read_config_for_env_reads_json(tmp_path):
    config_path = tmp_path / "config.custom.json"
    config_path.write_text("{\"APP_NAME\": \"Custom-Bot\"}", encoding="utf-8")

    original_config_files = dict(_persistence.CONFIG_FILES)
    _persistence.CONFIG_FILES["custom"] = str(config_path)

    try:
        data = _persistence.read_config_for_env("custom")
        assert data == {"APP_NAME": "Custom-Bot"}
    finally:
        _persistence.CONFIG_FILES.clear()
        _persistence.CONFIG_FILES.update(original_config_files)
