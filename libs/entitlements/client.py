"""Simple HTTP client for the entitlements service."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

import httpx


class EntitlementsError(Exception):
    """Raised when the entitlements service answers with an error."""


class QuotaExceeded(EntitlementsError):
    """Raised when a quota requirement cannot be satisfied."""


@dataclass(slots=True)
class Entitlements:
    """Represents the result of an entitlement resolution."""

    customer_id: str
    features: Dict[str, bool]
    quotas: Dict[str, Optional[int]]

    def has(self, capability: str) -> bool:
        return self.features.get(capability, False)

    def quota(self, name: str) -> Optional[int]:
        return self.quotas.get(name)


class EntitlementsClient:
    """Lightweight client wrapping :mod:`httpx`."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 5.0,
        api_key: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._api_key = api_key
        self._async_client: httpx.AsyncClient | None = None

    async def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None:
            headers = {}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._async_client = httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout, headers=headers)
        return self._async_client

    async def aclose(self) -> None:
        if self._async_client is not None:
            await self._async_client.aclose()
            self._async_client = None

    async def resolve(self, customer_id: str) -> Entitlements:
        client = await self._get_async_client()
        resp = await client.get("/entitlements/resolve", params={"customer_id": customer_id})
        if resp.status_code >= 400:
            raise EntitlementsError(resp.text)
        payload = resp.json()
        return Entitlements(
            customer_id=payload["customer_id"],
            features=payload.get("capabilities", {}),
            quotas=payload.get("quotas", {}),
        )

    def resolve_sync(self, customer_id: str) -> Entitlements:
        return asyncio.run(self.resolve(customer_id))

    async def require(
        self,
        customer_id: str,
        capabilities: Iterable[str] | None = None,
        quotas: Dict[str, int] | None = None,
    ) -> Entitlements:
        ent = await self.resolve(customer_id)
        capabilities = capabilities or []
        quotas = quotas or {}
        missing = [cap for cap in capabilities if not ent.has(cap)]
        if missing:
            raise EntitlementsError(f"Missing capabilities: {', '.join(missing)}")
        for quota_name, required in quotas.items():
            limit = ent.quota(quota_name)
            if limit is not None and limit < required:
                raise QuotaExceeded(f"Quota {quota_name}={limit} < required {required}")
        return ent

    async def __aenter__(self) -> "EntitlementsClient":
        await self._get_async_client()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()


__all__ = ["EntitlementsClient", "Entitlements", "EntitlementsError", "QuotaExceeded"]
