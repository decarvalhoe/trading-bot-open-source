from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


class TopStepAdapter:
    """Asynchronous client for TopStep's evaluation API."""

    def __init__(
        self,
        *,
        base_url: str,
        client_id: str,
        client_secret: str,
        http_client: httpx.AsyncClient | None = None,
        auth_path: str = "/oauth/token",
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = http_client or httpx.AsyncClient(base_url=self._base_url, timeout=timeout)
        self._client_owned = http_client is None
        self._client_id = client_id
        self._client_secret = client_secret
        self._auth_path = auth_path
        self._token: str | None = None
        self._token_expiry: datetime | None = None
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        if self._client_owned:
            await self._client.aclose()

    async def get_account_metrics(self, account_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v1/accounts/{account_id}/metrics")

    async def get_performance_history(
        self,
        account_id: str,
        *,
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return await self._request(
            "GET",
            f"/v1/accounts/{account_id}/performance",
            params=params,
        )

    async def get_risk_rules(self, account_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v1/accounts/{account_id}/risk-rules")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = await self._ensure_token()
        headers = {"Authorization": f"Bearer {token}"}

        response = await self._client.request(
            method,
            path,
            headers=headers,
            params=params,
        )

        if response.status_code == 401:
            token = await self._ensure_token(force_refresh=True)
            headers["Authorization"] = f"Bearer {token}"
            response = await self._client.request(
                method,
                path,
                headers=headers,
                params=params,
            )

        response.raise_for_status()
        return response.json()

    async def _ensure_token(self, *, force_refresh: bool = False) -> str:
        async with self._lock:
            if not force_refresh and self._token and self._token_expiry:
                now = datetime.now(timezone.utc)
                if now < self._token_expiry:
                    return self._token

            token, expires_in = await self._authenticate()
            self._token = token
            expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            # Refresh slightly before actual expiry to avoid race conditions
            self._token_expiry = expiry - timedelta(seconds=30)
            return self._token

    async def _authenticate(self) -> tuple[str, int]:
        response = await self._client.post(
            self._auth_path,
            json={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        expires_in = int(payload.get("expires_in", 0))
        if not token or expires_in <= 0:
            raise httpx.HTTPError("Invalid authentication response")
        return token, expires_in


__all__ = ["TopStepAdapter"]
