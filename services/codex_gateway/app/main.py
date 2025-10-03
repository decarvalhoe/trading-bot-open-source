"""FastAPI application receiving Codex webhooks."""

from __future__ import annotations

import json
from typing import Any

from fastapi import Depends, FastAPI, Request, status

from libs.codex import CodexEvent, CodexEventPayload
from libs.observability.logging import RequestContextMiddleware, configure_logging
from libs.observability.metrics import setup_metrics

from .config import Settings, get_settings
from .deps import get_broker
from .security import verify_github_signature, verify_stripe_signature, verify_tradingview_signature

configure_logging("codex-gateway")

app = FastAPI(title="Codex Gateway", version="0.1.0")
app.add_middleware(RequestContextMiddleware, service_name="codex-gateway")
setup_metrics(app, service_name="codex-gateway")


def _extract_event_type(body: bytes) -> str | None:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    event_type = payload.get("type")
    if isinstance(event_type, str):
        return event_type
    return None


@app.post("/webhooks/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    request: Request,
    settings: Settings = Depends(get_settings),
    broker=Depends(get_broker),
) -> dict[str, Any]:
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    verify_github_signature(settings.github_webhook_secret, signature, body)

    event = CodexEvent(
        provider="github",
        eventType=request.headers.get("X-GitHub-Event"),
        delivery=request.headers.get("X-GitHub-Delivery"),
        signature=signature,
        payload=CodexEventPayload(
            contentType=request.headers.get("Content-Type", "application/json"),
            body=body,
        ),
        metadata={
            "user_agent": request.headers.get("User-Agent", ""),
            "hook_id": request.headers.get("X-GitHub-Hook-ID", ""),
        },
    )
    await broker.publish(event)
    return {"status": "queued"}


@app.post("/webhooks/stripe", status_code=status.HTTP_202_ACCEPTED)
async def stripe_webhook(
    request: Request,
    settings: Settings = Depends(get_settings),
    broker=Depends(get_broker),
) -> dict[str, Any]:
    body = await request.body()
    signature = request.headers.get("stripe-signature")
    verify_stripe_signature(settings.stripe_webhook_secret, signature, body)

    event = CodexEvent(
        provider="stripe",
        eventType=_extract_event_type(body),
        signature=signature,
        payload=CodexEventPayload(
            contentType=request.headers.get("Content-Type", "application/json"),
            body=body,
        ),
        metadata={"stripe_event_id": request.headers.get("Stripe-Signature-Id", "")},
    )
    await broker.publish(event)
    return {"status": "queued"}


@app.post("/webhooks/tradingview", status_code=status.HTTP_202_ACCEPTED)
async def tradingview_webhook(
    request: Request,
    settings: Settings = Depends(get_settings),
    broker=Depends(get_broker),
) -> dict[str, Any]:
    body = await request.body()
    signature = request.headers.get("X-Signature")
    verify_tradingview_signature(settings.tradingview_webhook_secret, signature, body)

    event = CodexEvent(
        provider="tradingview",
        eventType=_extract_event_type(body),
        signature=signature,
        payload=CodexEventPayload(
            contentType=request.headers.get("Content-Type", "application/json"),
            body=body,
        ),
        metadata={"user_agent": request.headers.get("User-Agent", "")},
    )
    await broker.publish(event)
    return {"status": "queued"}


@app.get("/health", status_code=status.HTTP_200_OK)
async def health() -> dict[str, str]:
    return {"status": "ok"}
