"""Prometheus metrics helpers for FastAPI services."""

from __future__ import annotations

import time

from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

_REQUEST_COUNTER = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    labelnames=("service", "method", "path", "status"),
)
_REQUEST_LATENCY = Histogram(
    "http_request_latency_seconds",
    "Latency of HTTP requests in seconds",
    labelnames=("service", "method", "path"),
    buckets=(
        0.05,
        0.1,
        0.25,
        0.5,
        0.75,
        1.0,
        2.5,
        5.0,
        7.5,
        10.0,
    ),
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Collect basic request metrics for Prometheus."""

    def __init__(self, app: ASGIApp, *, service_name: str) -> None:
        super().__init__(app)
        self._service_name = service_name

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        route = request.scope.get("route")
        path_template: str = getattr(route, "path", request.url.path)
        method = request.method.upper()
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration = time.perf_counter() - start
            _REQUEST_COUNTER.labels(self._service_name, method, path_template, "500").inc()
            _REQUEST_LATENCY.labels(self._service_name, method, path_template).observe(duration)
            raise
        duration = time.perf_counter() - start
        status_code = getattr(response, "status_code", 500)
        _REQUEST_COUNTER.labels(self._service_name, method, path_template, str(status_code)).inc()
        _REQUEST_LATENCY.labels(self._service_name, method, path_template).observe(duration)
        return response


def setup_metrics(app: FastAPI, *, service_name: str) -> None:
    """Attach Prometheus metrics middleware and endpoint."""

    if getattr(app.state, "_metrics_configured", False):
        return

    app.add_middleware(MetricsMiddleware, service_name=service_name)

    async def metrics_endpoint() -> Response:
        payload = generate_latest()
        return Response(content=payload, media_type=CONTENT_TYPE_LATEST)

    app.add_api_route(
        "/metrics",
        metrics_endpoint,
        methods=["GET"],
        include_in_schema=False,
        name="metrics",
    )
    app.state._metrics_configured = True
