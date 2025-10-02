from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

_service_root = Path(__file__).resolve().parents[1]
_package_name = "config_service_app"
_repo_root = _service_root.parents[1]

if str(_repo_root) not in sys.path:
    sys.path.append(str(_repo_root))

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
persistence = importlib.import_module(f"{_package_name}.persistence")
schemas = importlib.import_module(f"{_package_name}.schemas")
settings_module = importlib.import_module(f"{_package_name}.settings")

app = main.app  # type: ignore[attr-defined]
ConfigUpdate = schemas.ConfigUpdate
Settings = settings_module.Settings
load_settings = settings_module.load_settings
read_config_for_env = persistence.read_config_for_env
CONFIG_FILES = persistence.CONFIG_FILES
