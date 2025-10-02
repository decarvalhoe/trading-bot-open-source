"""Dependency helpers for the marketplace service."""
from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, HTTPException, Request

from libs.entitlements.client import Entitlements

from .payments import StripeConnectGateway

def get_entitlements(request: Request) -> Entitlements:
    entitlements = getattr(request.state, "entitlements", None)
    if entitlements is None:
        raise HTTPException(status_code=403, detail="Entitlements are required")
    return entitlements


def require_publish_capability(entitlements: Entitlements = Depends(get_entitlements)) -> Entitlements:
    if not entitlements.has("can.publish_strategy"):
        raise HTTPException(status_code=403, detail="Missing capability: can.publish_strategy")
    return entitlements


def require_copy_capability(entitlements: Entitlements = Depends(get_entitlements)) -> Entitlements:
    if not entitlements.has("can.copy_trade"):
        raise HTTPException(status_code=403, detail="Missing capability: can.copy_trade")
    return entitlements


def get_actor_id(request: Request) -> str:
    actor_id = request.headers.get("x-user-id") or request.headers.get("x-customer-id")
    if not actor_id:
        raise HTTPException(status_code=400, detail="Missing x-user-id header")
    return actor_id


@lru_cache
def _payments_gateway() -> StripeConnectGateway:
    return StripeConnectGateway()


def get_payments_gateway() -> StripeConnectGateway:
    return _payments_gateway()


__all__ = [
    "get_entitlements",
    "require_publish_capability",
    "require_copy_capability",
    "get_actor_id",
    "get_payments_gateway",
]
