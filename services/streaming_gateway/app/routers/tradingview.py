"""TradingView webhook handler."""

from __future__ import annotations

import base64
import hmac
from hashlib import sha256
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError

from ..config import Settings
from ..deps import get_settings_dependency
from ..models import TradingViewWebhook

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_PROCESSED_EVENTS: set[str] = set()


@router.post("/tradingview")
async def tradingview_webhook(
    request: Request,
    settings: Settings = Depends(get_settings_dependency),
) -> Dict[str, str]:
    raw_body = await request.body()
    if settings.tradingview_hmac_secret:
        provided_signature = request.headers.get("x-signature")
        if not provided_signature:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Missing signature header"
            )
        digest = hmac.new(
            settings.tradingview_hmac_secret.encode("utf-8"), raw_body, sha256
        ).digest()
        expected_signature = base64.b64encode(digest).decode("utf-8")
        if not hmac.compare_digest(provided_signature, expected_signature):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")
    try:
        payload = TradingViewWebhook.parse_raw(raw_body)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    idempotency_key = request.headers.get("x-idempotency-key")
    if idempotency_key and idempotency_key in _PROCESSED_EVENTS:
        return {"status": "ignored", "reason": "duplicate"}
    if idempotency_key:
        _PROCESSED_EVENTS.add(idempotency_key)
    return {
        "status": "accepted",
        "symbol": payload.symbol,
        "side": payload.side,
        "timeframe": payload.timeframe,
    }
