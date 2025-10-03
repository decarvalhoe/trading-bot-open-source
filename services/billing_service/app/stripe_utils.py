"""Utilities for dealing with Stripe webhooks and API objects."""
from __future__ import annotations

import hmac
import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Dict, Optional

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


def _normalise_interval(interval: str | None) -> str:
    if not interval:
        return "monthly"
    interval = interval.lower()
    if interval in {"month", "monthly"}:
        return "monthly"
    if interval in {"year", "annual", "annually"}:
        return "annual"
    return interval


def _extract_connect_details(subscription: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    fallback_reference = subscription.get("id")
    invoice = subscription.get("latest_invoice")
    if isinstance(invoice, dict):
        payment_intent = invoice.get("payment_intent")
    else:
        payment_intent = None
    if isinstance(payment_intent, dict):
        transfer_data = payment_intent.get("transfer_data") or {}
        connect_account_id = transfer_data.get("destination") or payment_intent.get("on_behalf_of")
        charges = payment_intent.get("charges") or {}
        transfer_reference = None
        if isinstance(charges, dict):
            data = charges.get("data") or []
            if data:
                charge = data[0] or {}
                transfer_reference = charge.get("transfer") or charge.get("balance_transaction")
        if not transfer_reference:
            transfer_reference = payment_intent.get("id") or fallback_reference
        return connect_account_id, transfer_reference
    return None, fallback_reference


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
            billing_interval=_normalise_interval(plan_data.get("interval")),
            trial_period_days=plan_data.get("trial_period_days"),
        )
        connect_account_id, payment_reference = _extract_connect_details(data_object)
        update_subscription(
            db,
            customer_id=data_object.get("customer"),
            plan=plan,
            status=data_object.get("status", "active"),
            current_period_end=datetime.fromtimestamp(
                data_object.get("current_period_end", 0), timezone.utc
            )
            if data_object.get("current_period_end")
            else None,
            trial_end=datetime.fromtimestamp(data_object.get("trial_end", 0), timezone.utc)
            if data_object.get("trial_end")
            else None,
            connect_account_id=connect_account_id,
            payment_reference=payment_reference,
        )
    elif event_type == "customer.subscription.deleted":
        customer_id = data_object.get("customer")
        if customer_id:
            deactivate_subscription(db, customer_id=customer_id)
    return {"received": True}


def subscription_payload_from_stripe(subscription: Dict[str, Any], plan: Plan) -> Dict[str, Any]:
    connect_account_id, payment_reference = _extract_connect_details(subscription)
    return {
        "customer_id": subscription["customer"],
        "plan_id": plan.id,
        "status": subscription.get("status", "active"),
        "current_period_end": datetime.fromtimestamp(
            subscription.get("current_period_end", 0), timezone.utc
        )
        if subscription.get("current_period_end")
        else None,
        "trial_end": datetime.fromtimestamp(subscription.get("trial_end", 0), timezone.utc)
        if subscription.get("trial_end")
        else None,
        "connect_account_id": connect_account_id,
        "payment_reference": payment_reference,
    }


def parse_stripe_payload(raw_body: bytes) -> Dict[str, Any]:
    try:
        return json.loads(raw_body)
    except json.JSONDecodeError as exc:  # pragma: no cover - FastAPI already validates JSON
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Invalid JSON") from exc
