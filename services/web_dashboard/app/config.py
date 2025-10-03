"""Configuration helpers for the web dashboard."""

from __future__ import annotations

import os


def default_service_url(service: str) -> str:
    """Return the default URL for a service used by the dashboard.

    The dashboard can run in two contexts:

    * When executed inside the Docker network, services are reachable via
      ``http://<service>:8000``.
    * When executed natively on the host machine, services are exposed through
      loopback sub-domains (``http://<service>.localhost:8000``).
    """

    native_host = os.getenv("WEB_DASHBOARD_NATIVE_HOST")
    if native_host:
        return f"http://{service}.localhost:8000"
    return f"http://{service}:8000"
