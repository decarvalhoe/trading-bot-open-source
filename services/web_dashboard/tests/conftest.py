import contextlib
import importlib
import os
import sys
import threading
import time
import asyncio
from typing import Generator

import pytest
import uvicorn

from .utils import (
    AUTH_SERVICE_PACKAGE_NAME,
    load_auth_service_app,
    load_auth_service_module,
    load_dashboard_app,
    load_user_service_app,
    load_user_service_module,
)

TEST_JWT_SECRET = "test-onboarding-secret"


@pytest.fixture(scope="session")
def event_loop():
    """Provide a session-scoped event loop compatible with pytest-asyncio strict mode."""

    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest.fixture(scope="session")
def user_service_base_url(tmp_path_factory) -> Generator[str, None, None]:
    """Launch user-service with a temporary SQLite database for onboarding tests."""

    db_path = tmp_path_factory.mktemp("user-service") / "onboarding.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["JWT_SECRET"] = TEST_JWT_SECRET
    os.environ.setdefault("ENTITLEMENTS_BYPASS", "1")
    sys.modules.pop("libs.db.db", None)

    module = load_user_service_module()
    db_module = importlib.import_module("libs.db.db")
    module.Base.metadata.create_all(bind=db_module.engine)

    app = load_user_service_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    sock = config.bind_socket()
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()

    start_time = time.time()
    while not server.started:
        if time.time() - start_time > 10:
            raise RuntimeError("User service test server failed to start in time")
        time.sleep(0.05)

    host, port = sock.getsockname()[:2]
    base_url = f"http://{host}:{port}"

    try:
        yield base_url
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        with contextlib.suppress(Exception):
            sock.close()


@pytest.fixture(scope="session")
def auth_service_base_url(tmp_path_factory) -> Generator[str, None, None]:
    """Launch auth-service with a temporary SQLite database for account flows."""

    db_path = tmp_path_factory.mktemp("auth-service") / "auth.db"
    previous_db = os.environ.get("DATABASE_URL")
    previous_secret = os.environ.get("JWT_SECRET")
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["JWT_SECRET"] = TEST_JWT_SECRET
    os.environ.setdefault("ENTITLEMENTS_BYPASS", "1")
    sys.modules.pop("libs.db.db", None)

    module = load_auth_service_module()
    db_module = importlib.import_module("libs.db.db")
    models_module = importlib.import_module(f"{AUTH_SERVICE_PACKAGE_NAME}.app.models")
    models_module.Base.metadata.create_all(bind=db_module.engine)

    app = load_auth_service_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    sock = config.bind_socket()
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()

    start_time = time.time()
    while not server.started:
        if time.time() - start_time > 10:
            raise RuntimeError("Auth service test server failed to start in time")
        time.sleep(0.05)

    host, port = sock.getsockname()[:2]
    base_url = f"http://{host}:{port}"

    try:
        yield base_url
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        with contextlib.suppress(Exception):
            sock.close()
        if previous_db is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_db
        if previous_secret is None:
            os.environ.pop("JWT_SECRET", None)
        else:
            os.environ["JWT_SECRET"] = previous_secret


@pytest.fixture(scope="session")
def dashboard_app(user_service_base_url, auth_service_base_url):
    """Expose the FastAPI application for integration and E2E tests."""

    os.environ.setdefault("WEB_DASHBOARD_USER_SERVICE_URL", user_service_base_url)
    os.environ.setdefault("USER_SERVICE_JWT_SECRET", TEST_JWT_SECRET)
    os.environ.setdefault("WEB_DASHBOARD_DEFAULT_USER_ID", "1")
    os.environ.setdefault("WEB_DASHBOARD_AUTH_SERVICE_URL", auth_service_base_url)
    os.environ.setdefault("AUTH_SERVICE_URL", auth_service_base_url)
    os.environ.setdefault("WEB_DASHBOARD_ALGO_ENGINE_URL", "http://algo-engine:8000/")
    os.environ.setdefault("WEB_DASHBOARD_REPORTS_BASE_URL", "http://reports:8000/")
    os.environ.setdefault("WEB_DASHBOARD_ORDER_ROUTER_BASE_URL", "http://order-router:8000/")
    os.environ.setdefault("WEB_DASHBOARD_MARKETPLACE_URL", "http://marketplace:8000/")
    load_dashboard_app.cache_clear()
    return load_dashboard_app()


@pytest.fixture(scope="session")
def dashboard_base_url(dashboard_app) -> Generator[str, None, None]:
    """Launch the dashboard service with uvicorn for browser-based tests."""

    config = uvicorn.Config(dashboard_app, host="127.0.0.1", port=0, log_level="warning")
    sock = config.bind_socket()
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()

    start_time = time.time()
    while not server.started:
        if time.time() - start_time > 10:
            raise RuntimeError("Dashboard test server failed to start in time")
        time.sleep(0.05)

    host, port = sock.getsockname()[:2]
    base_url = f"http://{host}:{port}"

    try:
        yield base_url
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        with contextlib.suppress(Exception):
            sock.close()
