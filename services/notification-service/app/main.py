"""FastAPI application exposing the notification dispatcher."""

from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, HTTPException

from .config import Settings, get_settings
from .dispatcher import NotificationDispatcher
from .schemas import NotificationRequest, NotificationResponse

logger = logging.getLogger(__name__)


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

