"""Unit tests covering webhook signature validation."""

from __future__ import annotations

import base64
import hmac
from hashlib import sha256
from time import time

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from libs.codex import MemoryEventBroker
from services.codex_gateway.app import deps
from services.codex_gateway.app.config import Settings, get_settings
from services.codex_gateway.app.main import app


@pytest.fixture(autouse=True)
def reset_dependencies() -> None:
    deps.get_broker.__dict__.pop("_broker", None)
    app.dependency_overrides.clear()


@pytest.fixture()
def configured_settings() -> Settings:
    return Settings(
        github_webhook_secret="gh-secret",
        stripe_webhook_secret="stripe-secret",
        tradingview_webhook_secret="tv-secret",
    )


@pytest.mark.asyncio
async def test_github_webhook_enqueues_event(configured_settings: Settings) -> None:
    broker = MemoryEventBroker()
    app.dependency_overrides[deps.get_broker] = lambda: broker
    app.dependency_overrides[get_settings] = lambda: configured_settings

    body = b'{"action": "created"}'
    signature = hmac.new(b"gh-secret", body, sha256).hexdigest()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": f"sha256={signature}",
                "X-GitHub-Event": "issue_comment",
                "X-GitHub-Delivery": "delivery-1",
            },
        )

    assert response.status_code == status.HTTP_202_ACCEPTED
    event = await broker.get()
    assert event.provider == "github"
    assert event.event_type == "issue_comment"
    assert event.delivery == "delivery-1"
    assert event.payload.body == body


@pytest.mark.asyncio
async def test_github_webhook_rejects_invalid_signature(configured_settings: Settings) -> None:
    app.dependency_overrides[get_settings] = lambda: configured_settings

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhooks/github",
            content=b"{}",
            headers={"X-Hub-Signature-256": "sha256=invalid"},
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_stripe_webhook_verifies_signature(configured_settings: Settings) -> None:
    broker = MemoryEventBroker()
    app.dependency_overrides[deps.get_broker] = lambda: broker
    app.dependency_overrides[get_settings] = lambda: configured_settings

    body = b'{"type": "checkout.session.completed"}'
    timestamp = int(time())
    signed_payload = f"{timestamp}.{body.decode('utf-8')}".encode("utf-8")
    signature = hmac.new(b"stripe-secret", msg=signed_payload, digestmod=sha256).hexdigest()
    header = f"t={timestamp},v1={signature}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhooks/stripe",
            content=body,
            headers={"stripe-signature": header},
        )

    assert response.status_code == status.HTTP_202_ACCEPTED
    event = await broker.get()
    assert event.provider == "stripe"
    assert event.event_type == "checkout.session.completed"


@pytest.mark.asyncio
async def test_tradingview_webhook_verifies_signature(configured_settings: Settings) -> None:
    broker = MemoryEventBroker()
    app.dependency_overrides[deps.get_broker] = lambda: broker
    app.dependency_overrides[get_settings] = lambda: configured_settings

    body = b'{"type": "alert"}'
    digest = hmac.new(b"tv-secret", body, sha256).digest()
    signature = base64.b64encode(digest).decode("utf-8")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhooks/tradingview",
            content=body,
            headers={"X-Signature": signature},
        )

    assert response.status_code == status.HTTP_202_ACCEPTED
    event = await broker.get()
    assert event.provider == "tradingview"
    assert event.event_type == "alert"
