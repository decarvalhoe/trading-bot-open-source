from __future__ import annotations

from typing import Any

import httpx


class MarketDataClient:
    """Client used to interact with the market data service."""

    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._own_client = client is None
        self._client = client or httpx.AsyncClient(base_url=base_url)
        self._base_url = base_url

    async def fetch_context(self, symbol: str) -> dict[str, Any]:
        response = await self._client.get(f"/symbols/{symbol}/context")
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise TypeError("Market data context response must be a JSON object")
        return data

    async def aclose(self) -> None:
        if self._own_client:
            await self._client.aclose()


class ReportsClient:
    """Client used to fetch analytics from the reports service."""

    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._own_client = client is None
        self._client = client or httpx.AsyncClient(base_url=base_url)

    async def fetch_context(self, symbol: str) -> dict[str, Any]:
        response = await self._client.get(f"/symbols/{symbol}/summary")
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise TypeError("Reports context response must be a JSON object")
        return data

    async def aclose(self) -> None:
        if self._own_client:
            await self._client.aclose()


class NotificationPublisher:
    """Client responsible for pushing validated alerts to the notification service."""

    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._own_client = client is None
        self._client = client or httpx.AsyncClient(base_url=base_url)

    async def publish(self, payload: dict[str, Any]) -> None:
        response = await self._client.post("/notifications/alerts", json=payload)
        response.raise_for_status()

    async def aclose(self) -> None:
        if self._own_client:
            await self._client.aclose()
