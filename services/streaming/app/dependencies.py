from __future__ import annotations

import os
from typing import Iterable

from fastapi import HTTPException, Request, status

from libs.entitlements.client import EntitlementsClient, EntitlementsError
from libs.secrets import get_secret

from .config import Settings, get_settings
from .pipeline import StreamingBridge


async def get_bridge(request: Request) -> StreamingBridge:
    bridge: StreamingBridge | None = getattr(request.app.state, "bridge", None)
    if bridge is None:  # pragma: no cover - sanity guard for misconfigured tests
        raise RuntimeError("Streaming bridge non initialisé")
    return bridge


async def get_settings_dependency() -> Settings:
    return get_settings()


async def require_capability(request: Request, capability: str) -> None:
    entitlements = getattr(request.state, "entitlements", None)
    if entitlements is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Entitlements non résolus")
    if not entitlements.has(capability):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"Manque la capacité {capability}")


async def authorize_service(request: Request, allowed_tokens: Iterable[str | None]) -> None:
    token = request.headers.get("x-service-token")
    if token and token in [t for t in allowed_tokens if t]:
        return
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Jeton de service invalide")


class WebsocketAuthorizer:
    """Validation d'accès pour les connexions WebSocket."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._bypass = os.getenv("ENTITLEMENTS_BYPASS", "0") == "1"
        base_url = os.getenv("ENTITLEMENTS_SERVICE_URL", "http://entitlements-service:8000")
        api_key = get_secret("ENTITLEMENTS_SERVICE_API_KEY", default=os.getenv("ENTITLEMENTS_SERVICE_API_KEY"))
        self._client = EntitlementsClient(base_url, api_key=api_key)

    async def authorize(self, websocket) -> str:
        candidate = (
            websocket.query_params.get("viewer")
            or websocket.query_params.get("token")
            or websocket.headers.get("x-customer-id")
            or websocket.headers.get("x-user-id")
        )
        try:
            return await self._validate_customer(candidate)
        except HTTPException:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            raise

    async def authorize_request(self, request: Request) -> str:
        candidate = request.headers.get("x-customer-id") or request.headers.get("x-user-id")
        return await self._validate_customer(candidate)

    async def _validate_customer(self, customer_id: str | None) -> str:
        if not customer_id:
            if self._bypass:
                return "anonymous"
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Missing x-customer-id header")
        if self._bypass:
            return customer_id
        try:
            await self._client.require(customer_id, capabilities=[self._settings.entitlements_capability])
        except EntitlementsError as exc:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        return customer_id


__all__ = [
    "get_bridge",
    "get_settings_dependency",
    "require_capability",
    "authorize_service",
    "WebsocketAuthorizer",
]
