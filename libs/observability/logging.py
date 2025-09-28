"""Structured logging helpers shared by FastAPI services."""

from __future__ import annotations

import contextvars
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

_CORRELATION_ID_CTX: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)
_REQUEST_ID_CTX: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)
_CONFIGURED_SERVICES: set[str] = set()


class CorrelationIdFilter(logging.Filter):
    """Inject correlation identifiers into log records."""

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self._service_name = service_name

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - logging side effect
        record.service = self._service_name
        record.correlation_id = _CORRELATION_ID_CTX.get()
        record.request_id = _REQUEST_ID_CTX.get()
        return True


class JsonLogFormatter(logging.Formatter):
    """Format log records as JSON with a consistent schema."""

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self._service_name = service_name

    def format(self, record: logging.LogRecord) -> str:  # pragma: no cover - formatting side effect
        payload: dict[str, Any] = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "service": getattr(record, "service", self._service_name),
            "message": record.getMessage(),
        }
        correlation_id = getattr(record, "correlation_id", None)
        if correlation_id:
            payload["correlation_id"] = correlation_id
        request_id = getattr(record, "request_id", None)
        if request_id:
            payload["request_id"] = request_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = record.stack_info

        reserved = _reserved_log_keys()
        for key, value in record.__dict__.items():
            if key in reserved or key in payload:
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except TypeError:
                payload[key] = str(value)
        return json.dumps(payload, default=str)


def _reserved_log_keys() -> set[str]:
    return {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
    }


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Populate correlation identifiers for each request."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        service_name: str,
        correlation_header: str = "X-Correlation-ID",
    ) -> None:
        super().__init__(app)
        self._service_name = service_name
        self._correlation_header = correlation_header

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        incoming = request.headers.get(self._correlation_header) or request.headers.get(
            "X-Request-ID"
        )
        correlation_id = incoming or uuid.uuid4().hex
        request_id = uuid.uuid4().hex

        token_corr = _CORRELATION_ID_CTX.set(correlation_id)
        token_req = _REQUEST_ID_CTX.set(request_id)
        request.state.correlation_id = correlation_id
        request.state.request_id = request_id

        response = None
        try:
            response = await call_next(request)
            response.headers.setdefault(self._correlation_header, correlation_id)
            response.headers.setdefault("X-Request-ID", request_id)
            return response
        finally:
            _CORRELATION_ID_CTX.reset(token_corr)
            _REQUEST_ID_CTX.reset(token_req)


def configure_logging(service_name: str) -> None:
    """Configure structured logging for the current service."""

    if service_name in _CONFIGURED_SERVICES:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter(service_name))
    handler.addFilter(CorrelationIdFilter(service_name))

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers = [handler]

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logger = logging.getLogger(logger_name)
        logger.handlers = [handler]
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.addFilter(CorrelationIdFilter(service_name))

    _CONFIGURED_SERVICES.add(service_name)


def get_correlation_id() -> Optional[str]:
    """Return the correlation identifier for the active request context."""

    return _CORRELATION_ID_CTX.get()


def get_request_id() -> Optional[str]:
    """Return the unique request identifier for the active request context."""

    return _REQUEST_ID_CTX.get()
