"""FastAPI application exposing the notification dispatcher."""

from __future__ import annotations

import logging
import os
from collections.abc import Generator

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from libs.alert_events import AlertEventBase, AlertEventRepository

from .config import Settings, get_settings
from .dispatcher import NotificationDispatcher
from .schemas import (
    AlertTriggerNotification,
    NotificationRequest,
    NotificationResponse,
)

logger = logging.getLogger(__name__)


EVENTS_DATABASE_URL = os.getenv(
    "NOTIFICATION_SERVICE_EVENTS_DATABASE_URL",
    os.getenv("ALERT_EVENTS_DATABASE_URL", "sqlite:///./alert_events.db"),
)
_events_engine = create_engine(EVENTS_DATABASE_URL, future=True)
AlertEventBase.metadata.create_all(bind=_events_engine)
EventsSessionLocal = sessionmaker(
    bind=_events_engine, autocommit=False, autoflush=False, future=True
)
_alert_events_repository = AlertEventRepository()


def get_events_session() -> Generator[Session, None, None]:
    session = EventsSessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_dispatcher(settings: Settings = Depends(get_settings)) -> NotificationDispatcher:
    """Provide a dispatcher instance bound to the current settings."""

    return NotificationDispatcher(settings)


app = FastAPI(title="Notification Service", version="0.1.0")


@app.get("/health")
def healthcheck() -> dict[str, str]:
    """Simple health endpoint."""

    return {"status": "ok"}


@app.post("/notifications", response_model=NotificationResponse, status_code=202)
async def send_notification(
    payload: NotificationRequest,
    dispatcher: NotificationDispatcher = Depends(get_dispatcher),
) -> NotificationResponse:
    """Dispatch a notification to the requested channel."""

    response = await dispatcher.dispatch(payload)
    if not response.delivered:
        raise HTTPException(status_code=502, detail=response.detail)
    return response


@app.post("/notifications/alerts", status_code=202)
def register_alert_event(
    payload: AlertTriggerNotification,
    session: Session = Depends(get_events_session),
) -> dict[str, object]:
    """Persist a trigger payload so it can be exposed through the history API."""

    repository = _alert_events_repository
    event = None
    if payload.event_id is not None:
        event = repository.get_by_id(session, payload.event_id)

    if event is None:
        event = repository.record_event(
            session,
            trigger_id=payload.trigger_id,
            rule_id=payload.rule_id,
            rule_name=payload.rule_name,
            strategy=payload.strategy,
            severity=payload.severity,
            symbol=payload.symbol,
            triggered_at=payload.triggered_at,
            context=payload.context,
            source="alert-engine",
            delivery_status="received",
            notification_channel=payload.notification_channel,
            notification_target=payload.notification_target,
        )
    else:
        event.trigger_id = payload.trigger_id
        event.rule_id = payload.rule_id
        event.rule_name = payload.rule_name
        event.strategy = payload.strategy
        event.severity = payload.severity
        event.symbol = payload.symbol
        event.triggered_at = payload.triggered_at
        event.context = payload.context
        event.notification_channel = payload.notification_channel
        event.notification_target = payload.notification_target
        event = repository.update_delivery(session, event, status="received")

    return {"event_id": event.id, "status": "recorded"}

