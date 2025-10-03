import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import ValidationError

CURRENT_DIR = Path(__file__).resolve().parent

HELPERS_NAME = "config_service_test_helpers"
HELPERS_PATH = CURRENT_DIR / "_helpers.py"


def _load_helpers(name: str, path: Path) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[arg-type]
    return module


helpers = _load_helpers(HELPERS_NAME, HELPERS_PATH)

CONFIG_FILES = helpers.CONFIG_FILES
ConfigUpdate = helpers.ConfigUpdate
Settings = helpers.Settings
load_settings = helpers.load_settings
read_config_for_env = helpers.read_config_for_env


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_current_config(client):
    response = client.get("/config/current")
    assert response.status_code == 200
    data = Settings.model_validate(response.json())
    assert data.APP_NAME == "trading-bot-config"


def test_update_config(client, config_env):
    config_path = Path(config_env) / "config.test.json"
    CONFIG_FILES["test"] = str(config_path)

    update_payload = ConfigUpdate(APP_NAME="My-Awesome-Trading-Bot")
    response = client.post("/config/update", json=update_payload.model_dump(exclude_none=True))
    assert response.status_code == 200
    data = Settings.model_validate(response.json())
    assert data.APP_NAME == "My-Awesome-Trading-Bot"
    assert data.ENVIRONMENT == "test"

    assert config_path.exists()
    assert "My-Awesome-Trading-Bot" in config_path.read_text(encoding="utf-8")

    CONFIG_FILES.pop("test", None)


def test_read_config_for_env_reads_json(tmp_path):
    config_path = tmp_path / "config.custom.json"
    config_path.write_text("{\"APP_NAME\": \"Custom-Bot\"}", encoding="utf-8")

    original_config_files = dict(CONFIG_FILES)
    CONFIG_FILES["custom"] = str(config_path)

    try:
        data = read_config_for_env("custom")
        assert data == {"APP_NAME": "Custom-Bot"}
    finally:
        CONFIG_FILES.clear()
        CONFIG_FILES.update(original_config_files)


def test_settings_environment_validation():
    with pytest.raises(ValidationError):
        Settings(ENVIRONMENT="invalid")


def test_config_update_rejects_incorrect_types():
    with pytest.raises(ValidationError):
        ConfigUpdate(APP_NAME=123)  # type: ignore[arg-type]


def test_load_settings_merges_environment_file(monkeypatch, tmp_path):
    config_path = tmp_path / "config.test.json"
    config_path.write_text("{\"APP_NAME\": \"Merged\", \"ENVIRONMENT\": \"test\"}", encoding="utf-8")

    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("CONFIG_DATA_DIR", str(tmp_path))
    CONFIG_FILES["test"] = str(config_path)

    try:
        merged = load_settings()
        assert merged.APP_NAME == "Merged"
        assert merged.ENVIRONMENT == "test"
    finally:
        CONFIG_FILES.pop("test", None)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("CONFIG_DATA_DIR", raising=False)
