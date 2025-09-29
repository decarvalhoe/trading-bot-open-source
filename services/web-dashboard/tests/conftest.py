from __future__ import annotations

import contextlib
import threading
import time
from typing import Generator

import pytest
import uvicorn

from .utils import load_dashboard_app


@pytest.fixture(scope="session")
def dashboard_app():
    """Expose the FastAPI application for integration and E2E tests."""

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

