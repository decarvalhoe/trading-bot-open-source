"""Test utilities for the web dashboard service."""

from __future__ import annotations

import importlib.util
import sys
import types
from functools import lru_cache
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "main.py"
PACKAGE_NAME = "web_dashboard"


@lru_cache(maxsize=1)
def load_dashboard_app():
    """Return the FastAPI application exposed by the dashboard service."""

    if "python_multipart" not in sys.modules:
        python_multipart_module = types.ModuleType("python_multipart")
        python_multipart_module.__version__ = "0.0.20"
        sys.modules.setdefault("python_multipart", python_multipart_module)

    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(MODULE_PATH.parents[1])]
    sys.modules.setdefault(PACKAGE_NAME, package)

    app_package_name = f"{PACKAGE_NAME}.app"
    app_package = types.ModuleType(app_package_name)
    app_package.__path__ = [str(MODULE_PATH.parent)]
    sys.modules.setdefault(app_package_name, app_package)

    spec = importlib.util.spec_from_file_location(
        f"{app_package_name}.main",
        MODULE_PATH,
        submodule_search_locations=[str(MODULE_PATH.parent)],
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive guard
        raise RuntimeError("Unable to load dashboard application module")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.app


__all__ = ["load_dashboard_app"]

