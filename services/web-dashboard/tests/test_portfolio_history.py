import importlib.util
import sys
import types
from pathlib import Path

from fastapi.testclient import TestClient


MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "main.py"
package_name = "web_dashboard"
package = types.ModuleType(package_name)
package.__path__ = [str(MODULE_PATH.parents[1])]
sys.modules.setdefault(package_name, package)

app_package_name = f"{package_name}.app"
app_package = types.ModuleType(app_package_name)
app_package.__path__ = [str(MODULE_PATH.parent)]
sys.modules.setdefault(app_package_name, app_package)

spec = importlib.util.spec_from_file_location(
    f"{app_package_name}.main", MODULE_PATH, submodule_search_locations=[str(MODULE_PATH.parent)]
)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)
app = module.app


client = TestClient(app)


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
