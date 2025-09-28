"""Signature validation utilities for webhook endpoints."""

from __future__ import annotations

import base64
import hmac
from hashlib import sha256
from time import time

from fastapi import HTTPException, status


def verify_github_signature(secret: str, signature_header: str | None, body: bytes) -> None:
    """Validate a GitHub webhook signature."""

    if not secret:
        return
    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing signature")
    signature = signature_header.split("=", 1)[1]
    expected = hmac.new(secret.encode("utf-8"), body, sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")


def verify_stripe_signature(secret: str, signature_header: str | None, body: bytes) -> None:
    """Validate a Stripe webhook signature."""

    if not secret:
        return
    if not signature_header:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing signature")

    elements: dict[str, str] = {}
    for part in signature_header.split(","):
        try:
            key, value = part.split("=", 1)
        except ValueError as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature header") from exc
        elements[key] = value

    timestamp = int(elements.get("t", "0"))
    transmitted_signature = elements.get("v1")
    if not transmitted_signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing signature")

    if abs(int(time()) - timestamp) > 300:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expired signature")

    signed_payload = f"{timestamp}.{body.decode('utf-8')}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), msg=signed_payload, digestmod=sha256).hexdigest()
    if not hmac.compare_digest(expected, transmitted_signature):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")


def verify_tradingview_signature(secret: str, signature_header: str | None, body: bytes) -> None:
    """Validate a TradingView webhook signature."""

    if not secret:
        return
    if not signature_header:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing signature")

    digest = hmac.new(secret.encode("utf-8"), body, sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")
