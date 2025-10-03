import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from schemathesis import openapi

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

ConfigUpdate = helpers.ConfigUpdate
Settings = helpers.Settings
app = helpers.app


def test_openapi_contract_validates_structure():
    schema = openapi.from_asgi("/openapi.json", app)
    schema.validate()
    assert "/config/current" in schema.raw_schema.get("paths", {})
    assert "/config/update" in schema.raw_schema.get("paths", {})


def test_contract_endpoints_return_declared_models(client, config_env):
    schema = openapi.from_asgi("/openapi.json", app)
    current_operation = schema["/config/current"]["get"]
    current_response = client.get("/config/current")
    current_operation.validate_response(current_response)

    payload = ConfigUpdate(APP_NAME="Contract-Bot").model_dump(exclude_none=True)
    update_operation = schema["/config/update"]["post"]
    response = client.post("/config/update", json=payload)
    Settings.model_validate(response.json())
    update_operation.validate_response(response)

    error_response = client.post("/config/update", json={"ENVIRONMENT": "invalid"})
    assert error_response.status_code == 400
