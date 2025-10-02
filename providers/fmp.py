"""Client for the Financial Modeling Prep screener API."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import httpx


class FinancialModelingPrepError(RuntimeError):
    """Raised when the Financial Modeling Prep API answers with an error."""


class FinancialModelingPrepClient:
    """Lightweight async client dedicated to the screener endpoint."""

    def __init__(
        self,
        api_key: Optional[str],
        *,
        base_url: str = "https://financialmodelingprep.com/api/v3",
        timeout: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = client
        self.name = "fmp"

    async def __aenter__(self) -> "FinancialModelingPrepClient":
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def screen(
        self, *, filters: Dict[str, Any] | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Execute the screener endpoint with the provided filters."""

        if self._client is None:
            raise RuntimeError("Client must be used as an async context manager")
        if not self._api_key:
            raise FinancialModelingPrepError("Missing Financial Modeling Prep API key")

        params: Dict[str, Any] = {"apikey": self._api_key, "limit": limit}
        if filters:
            for key, value in filters.items():
                if value is None:
                    continue
                if isinstance(value, (list, tuple, set)):
                    params[key] = ",".join(str(item) for item in value)
                elif isinstance(value, bool):
                    params[key] = json.dumps(value)
                else:
                    params[key] = value

        response = await self._client.get("/stock-screener", params=params)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:  # pragma: no cover - straight passthrough
            raise FinancialModelingPrepError(str(exc)) from exc

        payload = response.json()
        if not isinstance(payload, list):
            raise FinancialModelingPrepError("Unexpected response payload from FMP")
        return [row if isinstance(row, dict) else {"value": row} for row in payload]


__all__ = ["FinancialModelingPrepClient", "FinancialModelingPrepError"]
