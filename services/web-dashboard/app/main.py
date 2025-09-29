"""Minimal dashboard service for monitoring trading activity."""

from __future__ import annotations

import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Iterator
from urllib.parse import urljoin

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from libs.alert_events import AlertEventBase, AlertEventRepository

from .data import load_dashboard_context, load_portfolio_history
from .alerts_client import AlertsEngineClient, AlertsEngineError
from .schemas import Alert, AlertCreateRequest, AlertUpdateRequest


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Web Dashboard", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

STREAMING_BASE_URL = os.getenv("WEB_DASHBOARD_STREAMING_BASE_URL", "http://localhost:8001/")
STREAMING_ROOM_ID = os.getenv("WEB_DASHBOARD_STREAMING_ROOM_ID", "public-room")
STREAMING_VIEWER_ID = os.getenv("WEB_DASHBOARD_STREAMING_VIEWER_ID", "demo-viewer")
ALERT_ENGINE_BASE_URL = os.getenv("WEB_DASHBOARD_ALERT_ENGINE_URL", "http://alerts-engine:8000/")
ALERT_ENGINE_TIMEOUT = float(os.getenv("WEB_DASHBOARD_ALERT_ENGINE_TIMEOUT", "5.0"))

security = HTTPBearer(auto_error=False)


ALERT_EVENTS_DATABASE_URL = os.getenv(
    "WEB_DASHBOARD_ALERT_EVENTS_DATABASE_URL",
    os.getenv("ALERT_EVENTS_DATABASE_URL", "sqlite:///./alert_events.db"),
)

_alert_events_engine = create_engine(ALERT_EVENTS_DATABASE_URL, future=True)
AlertEventBase.metadata.create_all(bind=_alert_events_engine)
_alert_events_session_factory = sessionmaker(
    bind=_alert_events_engine, autocommit=False, autoflush=False, future=True
)
_alert_events_repository = AlertEventRepository()


def get_alert_events_session() -> Iterator[Session]:
    session = _alert_events_session_factory()
    try:
        yield session
    finally:
        session.close()


@lru_cache(maxsize=1)
def _alerts_client_factory() -> AlertsEngineClient:
    return AlertsEngineClient(base_url=ALERT_ENGINE_BASE_URL, timeout=ALERT_ENGINE_TIMEOUT)


def get_alerts_client() -> AlertsEngineClient:
    """Return a configured client for communicating with the alert engine."""

    return _alerts_client_factory()


def _handle_alert_engine_error(error: AlertsEngineError) -> None:
    status_code = error.status_code or status.HTTP_502_BAD_GATEWAY
    if status_code < 400 or status_code >= 600:
        status_code = status.HTTP_502_BAD_GATEWAY
    message = error.message or "Erreur du moteur d'alertes."
    raise HTTPException(status_code=status_code, detail=message)


def require_alerts_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> None:
    """Ensure alert management routes are protected by a bearer token when configured."""

    token = os.getenv("WEB_DASHBOARD_ALERTS_TOKEN")
    if not token:
        return
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise pour gérer les alertes.",
        )
    if credentials.credentials != token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Jeton d'authentification invalide.",
        )


@app.on_event("shutdown")
def shutdown_alerts_client() -> None:
    """Ensure HTTP resources opened for the alerts engine are properly released."""

    try:
        client = _alerts_client_factory()
    except Exception:  # pragma: no cover - defensive guard if instantiation fails
        return
    client.close()
    _alerts_client_factory.cache_clear()


@app.get("/health")
def healthcheck() -> dict[str, str]:
    """Simple health endpoint."""

    return {"status": "ok"}


@app.get("/portfolios")
def list_portfolios() -> dict[str, object]:
    """Return a snapshot of portfolios."""

    context = load_dashboard_context()
    return {"items": context.portfolios}


@app.get("/portfolios/history")
def portfolio_history() -> dict[str, object]:
    """Return historical valuation series for each portfolio."""

    history = load_portfolio_history()
    return {
        "items": [series.model_dump(mode="json") for series in history],
        "granularity": "daily",
    }


@app.get("/transactions")
def list_transactions() -> dict[str, object]:
    """Return recent transactions."""

    context = load_dashboard_context()
    return {"items": context.transactions}


@app.get("/alerts")
def list_alerts() -> dict[str, object]:
    """Return currently active alerts."""

    context = load_dashboard_context()
    return {"items": context.alerts}


@app.get("/alerts/history")
def list_alert_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    start: datetime | None = Query(None, description="Filter events triggered after this timestamp"),
    end: datetime | None = Query(None, description="Filter events triggered before this timestamp"),
    strategy: str | None = Query(None, description="Filter by strategy or rule name"),
    severity: str | None = Query(None, description="Filter by severity"),
    session: Session = Depends(get_alert_events_session),
) -> dict[str, object]:
    """Return paginated alert history entries."""

    page_data = _alert_events_repository.list_events(
        session,
        page=page,
        page_size=page_size,
        start=start,
        end=end,
        strategy=strategy,
        severity=severity,
    )

    items = [
        {
            "id": event.id,
            "trigger_id": event.trigger_id,
            "rule_id": event.rule_id,
            "rule_name": event.rule_name,
            "strategy": event.strategy,
            "severity": event.severity,
            "symbol": event.symbol,
            "triggered_at": event.triggered_at.isoformat(),
            "context": event.context or {},
            "delivery_status": event.delivery_status,
            "notification_channel": event.notification_channel,
            "notification_target": event.notification_target,
        }
        for event in page_data.items
    ]

    available_filters = {
        "strategies": _alert_events_repository.list_strategies(session),
        "severities": _alert_events_repository.list_severities(session),
    }

    return {
        "items": items,
        "pagination": {
            "page": page_data.page,
            "page_size": page_data.page_size,
            "total": page_data.total,
            "pages": page_data.pages,
        },
        "available_filters": available_filters,
    }


@app.post("/alerts", response_model=Alert, status_code=status.HTTP_201_CREATED)
def create_alert(
    alert: AlertCreateRequest,
    client: AlertsEngineClient = Depends(get_alerts_client),
    _: None = Depends(require_alerts_auth),
) -> Alert:
    """Create a new alert by delegating to the alert engine."""

    try:
        payload = client.create_alert(alert.model_dump(mode="json"))
    except AlertsEngineError as error:
        _handle_alert_engine_error(error)
    return Alert.model_validate(payload)


@app.put("/alerts/{alert_id}", response_model=Alert)
def update_alert(
    alert_id: str,
    payload: AlertUpdateRequest,
    client: AlertsEngineClient = Depends(get_alerts_client),
    _: None = Depends(require_alerts_auth),
) -> Alert:
    """Update an existing alert by delegating to the alert engine."""

    body = payload.model_dump(mode="json", exclude_unset=True)
    try:
        response_payload = client.update_alert(alert_id, body)
    except AlertsEngineError as error:
        _handle_alert_engine_error(error)

    merged = {"id": alert_id, **body, **(response_payload or {})}
    return Alert.model_validate(merged)


@app.delete("/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert(
    alert_id: str,
    client: AlertsEngineClient = Depends(get_alerts_client),
    _: None = Depends(require_alerts_auth),
) -> Response:
    """Remove an alert through the alert engine API."""

    try:
        client.delete_alert(alert_id)
    except AlertsEngineError as error:
        _handle_alert_engine_error(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/dashboard", response_class=HTMLResponse)
def render_dashboard(request: Request) -> HTMLResponse:
    """Render an HTML dashboard that surfaces key trading signals."""

    context = load_dashboard_context()
    handshake_url = urljoin(STREAMING_BASE_URL, f"rooms/{STREAMING_ROOM_ID}/connection")
    alerts_token = os.getenv("WEB_DASHBOARD_ALERTS_TOKEN", "")
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "context": context,
            "streaming": {
                "handshake_url": handshake_url,
                "room_id": STREAMING_ROOM_ID,
                "viewer_id": STREAMING_VIEWER_ID,
            },
            "alerts_api": {
                "endpoint": request.url_for("list_alerts"),
                "history_endpoint": request.url_for("list_alert_history"),
                "token": alerts_token,
            },
        },
    )


@app.get("/")
def root_redirect(request: Request) -> HTMLResponse:
    """Serve the dashboard at the root path for convenience."""

    return render_dashboard(request)

