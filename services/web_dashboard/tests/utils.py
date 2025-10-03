"""Test utilities for the web dashboard service."""

from __future__ import annotations

import importlib.util
import sys
import types
from functools import lru_cache
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "main.py"
PACKAGE_NAME = "web_dashboard"
USER_SERVICE_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "user_service" / "app" / "main.py"
)
USER_SERVICE_PACKAGE_NAME = "user_service_dashboard_proxy"
AUTH_SERVICE_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "auth_service" / "app" / "main.py"
)
AUTH_SERVICE_PACKAGE_NAME = "auth_service_dashboard_proxy"


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


@lru_cache(maxsize=1)
def load_user_service_module():
    """Load the user-service module for dashboard integration tests."""

    package = types.ModuleType(USER_SERVICE_PACKAGE_NAME)
    package.__path__ = [str(USER_SERVICE_MODULE_PATH.parents[1])]
    sys.modules.setdefault(USER_SERVICE_PACKAGE_NAME, package)

    spec = importlib.util.spec_from_file_location(
        f"{USER_SERVICE_PACKAGE_NAME}.main",
        USER_SERVICE_MODULE_PATH,
        submodule_search_locations=[str(USER_SERVICE_MODULE_PATH.parent)],
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive guard
        raise RuntimeError("Unable to load user-service application module")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_user_service_app():
    """Return the ASGI application exposed by the user-service."""

    return load_user_service_module().app


@lru_cache(maxsize=1)
def load_auth_service_module():
    """Load the auth-service module for dashboard integration tests."""

    package = types.ModuleType(AUTH_SERVICE_PACKAGE_NAME)
    package.__path__ = [str(AUTH_SERVICE_MODULE_PATH.parents[1])]
    sys.modules.setdefault(AUTH_SERVICE_PACKAGE_NAME, package)

    spec = importlib.util.spec_from_file_location(
        f"{AUTH_SERVICE_PACKAGE_NAME}.main",
        AUTH_SERVICE_MODULE_PATH,
        submodule_search_locations=[str(AUTH_SERVICE_MODULE_PATH.parent)],
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive guard
        raise RuntimeError("Unable to load auth-service application module")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_auth_service_app():
    """Return the ASGI application exposed by the auth-service."""

    return load_auth_service_module().app


__all__ = [
    "load_dashboard_app",
    "load_user_service_app",
    "load_user_service_module",
    "load_auth_service_app",
    "load_auth_service_module",
    "AUTH_SERVICE_PACKAGE_NAME",
]

