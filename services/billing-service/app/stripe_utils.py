"""Utilities for dealing with Stripe webhooks and API objects."""
from __future__ import annotations

import hmac
import json
from datetime import datetime
from hashlib import sha256
from typing import Any, Dict

from fastapi import HTTPException
from starlette.status import HTTP_400_BAD_REQUEST

from .service import deactivate_subscription, update_subscription, upsert_plan
from infra import Plan


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> None:
    """Validate the signature following Stripe's signing algorithm."""

    try:
        elements = dict(item.split("=", 1) for item in signature.split(","))
        timestamp = elements["t"]
        transmitted_signature = elements["v1"]
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Invalid signature header") from exc

    signed_payload = f"{timestamp}.{payload.decode()}".encode()
    expected = hmac.new(secret.encode(), msg=signed_payload, digestmod=sha256).hexdigest()
    if not hmac.compare_digest(expected, transmitted_signature):
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Signature mismatch")


def handle_stripe_event(event: Dict[str, Any], *, db) -> Dict[str, Any]:
    """Handle a Stripe webhook event and synchronise local state."""

    event_type = event.get("type", "")
    data_object = event.get("data", {}).get("object", {})
    if event_type in {"customer.subscription.created", "customer.subscription.updated"}:
        plan_data = data_object.get("plan") or {}
        plan_code = plan_data.get("nickname") or plan_data.get("id")
        if not plan_code:
            raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Missing plan code in event")
        plan = upsert_plan(
            db,
            code=plan_code,
            name=plan_data.get("nickname") or plan_code,
            stripe_price_id=plan_data.get("id", plan_code),
            description=plan_data.get("product"),
        )
        update_subscription(
            db,
            customer_id=data_object.get("customer"),
            plan=plan,
            status=data_object.get("status", "active"),
            current_period_end=datetime.utcfromtimestamp(data_object.get("current_period_end", 0))
            if data_object.get("current_period_end")
            else None,
        )
    elif event_type == "customer.subscription.deleted":
        customer_id = data_object.get("customer")
        if customer_id:
            deactivate_subscription(db, customer_id=customer_id)
    return {"received": True}


def subscription_payload_from_stripe(subscription: Dict[str, Any], plan: Plan) -> Dict[str, Any]:
    return {
        "customer_id": subscription["customer"],
        "plan_id": plan.id,
        "status": subscription.get("status", "active"),
        "current_period_end": datetime.utcfromtimestamp(subscription.get("current_period_end", 0))
        if subscription.get("current_period_end")
        else None,
    }


def parse_stripe_payload(raw_body: bytes) -> Dict[str, Any]:
    try:
        return json.loads(raw_body)
    except json.JSONDecodeError as exc:  # pragma: no cover - FastAPI already validates JSON
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Invalid JSON") from exc
