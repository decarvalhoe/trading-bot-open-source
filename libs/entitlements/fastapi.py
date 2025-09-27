"""FastAPI integration helpers for the entitlements client."""
from __future__ import annotations

import os
from typing import Dict, Iterable, Optional

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from .client import Entitlements, EntitlementsClient


class EntitlementsMiddleware(BaseHTTPMiddleware):
    """Fetch entitlements for the incoming user and enforce requirements."""

    def __init__(
        self,
        app,
        client: EntitlementsClient,
        *,
        required_capabilities: Optional[Iterable[str]] = None,
        required_quotas: Optional[Dict[str, int]] = None,
    ) -> None:
        super().__init__(app)
        self._client = client
        self._required_capabilities = list(required_capabilities or [])
        self._required_quotas = dict(required_quotas or {})
        self._bypass = os.getenv("ENTITLEMENTS_BYPASS", "0") == "1"

    async def dispatch(self, request: Request, call_next):
        customer_id = request.headers.get("x-customer-id") or request.headers.get("x-user-id")
        if not customer_id:
            if self._bypass:
                request.state.entitlements = Entitlements(customer_id="anonymous", features={}, quotas={})
                return await call_next(request)
            raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Missing x-customer-id header")

        try:
            entitlements = await self._client.require(
                customer_id,
                capabilities=self._required_capabilities,
                quotas=self._required_quotas,
            )
        except Exception as exc:  # pragma: no cover - the client already raises meaningful errors
            raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail=str(exc)) from exc

        request.state.entitlements = entitlements
        response = await call_next(request)
        return response


def install_entitlements_middleware(
    app,
    *,
    required_capabilities: Optional[Iterable[str]] = None,
    required_quotas: Optional[Dict[str, int]] = None,
) -> None:
    base_url = os.getenv("ENTITLEMENTS_SERVICE_URL", "http://entitlements-service:8000")
    api_key = os.getenv("ENTITLEMENTS_SERVICE_API_KEY")
    client = EntitlementsClient(base_url, api_key=api_key)
    app.add_middleware(
        EntitlementsMiddleware,
        client=client,
        required_capabilities=required_capabilities,
        required_quotas=required_quotas,
    )


__all__ = ["EntitlementsMiddleware", "install_entitlements_middleware"]
