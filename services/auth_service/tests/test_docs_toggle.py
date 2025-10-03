import importlib
import importlib.util
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

CURRENT_DIR = Path(__file__).resolve().parent

HELPERS_NAME = "auth_service_test_helpers"
HELPERS_PATH = CURRENT_DIR / "_helpers.py"
ENV_VAR = "AUTH_SERVICE_ENABLE_DOCS"
DOCS_ENDPOINTS = ("/docs", "/redoc", "/openapi.json")


def _load_helpers(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[arg-type]
    return module


helpers = _load_helpers(HELPERS_NAME, HELPERS_PATH)


def _set_env(value: bool | None) -> None:
    if value is None:
        os.environ.pop(ENV_VAR, None)
    else:
        os.environ[ENV_VAR] = "true" if value else "false"


def _reload_app(flag: bool | None):
    _set_env(flag)
    module = importlib.reload(helpers.main)
    helpers.main = module
    helpers.app = module.app
    return module.app


def test_docs_routes_respect_toggle():
    original_env = os.environ.get(ENV_VAR)
    try:
        app_with_docs = _reload_app(True)
        with TestClient(app_with_docs) as client:
            for endpoint in ("/docs", "/openapi.json"):
                response = client.get(endpoint)
                assert response.status_code == 200

        app_without_docs = _reload_app(False)
        with TestClient(app_without_docs) as client:
            for endpoint in DOCS_ENDPOINTS:
                response = client.get(endpoint)
                assert response.status_code == 404
    finally:
        if original_env is None:
            os.environ.pop(ENV_VAR, None)
        else:
            os.environ[ENV_VAR] = original_env
        restored = importlib.reload(helpers.main)
        helpers.main = restored
        helpers.app = restored.app

