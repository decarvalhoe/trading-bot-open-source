import contextlib
import importlib
import os
import sys
import threading
import time
from typing import Generator

import pytest
import uvicorn

from .utils import load_dashboard_app, load_user_service_app, load_user_service_module

TEST_JWT_SECRET = "test-onboarding-secret"


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
def dashboard_app(user_service_base_url):
    """Expose the FastAPI application for integration and E2E tests."""

    os.environ.setdefault("WEB_DASHBOARD_USER_SERVICE_URL", user_service_base_url)
    os.environ.setdefault("USER_SERVICE_JWT_SECRET", TEST_JWT_SECRET)
    os.environ.setdefault("WEB_DASHBOARD_DEFAULT_USER_ID", "1")
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
