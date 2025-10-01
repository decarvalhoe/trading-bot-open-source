"""HTTP client utilities for interacting with the order router service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from schemas.order_router import PaginatedOrders


class OrderRouterError(RuntimeError):
    """Raised when the order router returns an unexpected response."""

    def __init__(self, message: str, *, response: httpx.Response | None = None):
        super().__init__(message)
        self.response = response


@dataclass
class OrderRouterClient:
    """Tiny wrapper around the order-router HTTP API."""

    base_url: str
    timeout: float = 5.0
    transport: httpx.BaseTransport | None = None

    def __post_init__(self) -> None:
        self._client = httpx.Client(
            base_url=self.base_url, timeout=self.timeout, transport=self.transport
        )

    def __enter__(self) -> "OrderRouterClient":
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: Any) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def fetch_orders(self, *, limit: int = 100, offset: int = 0) -> PaginatedOrders:
        """Return a slice of the orders log."""

        response = self._client.get(
            "/orders/log",
            params={"limit": limit, "offset": offset},
            headers={"accept": "application/json"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise exc
        try:
            payload = response.json()
        except ValueError as exc:  # pragma: no cover - defensive guard for non JSON payloads
            raise OrderRouterError("Order router returned non JSON payload", response=response) from exc
        try:
            return PaginatedOrders.model_validate(payload)
        except ValidationError as exc:
            raise OrderRouterError("Unable to parse order router payload", response=response) from exc


__all__ = ["OrderRouterClient", "OrderRouterError"]
