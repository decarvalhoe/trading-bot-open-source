"""HTTP client utilities for interacting with the order router service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from pydantic import ValidationError

from schemas.order_router import (
    OrderRecord,
    PaginatedOrders,
    PositionCloseRequest,
    PositionCloseResponse,
    PositionsResponse,
)


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

    def fetch_orders(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        account_id: str | None = None,
        symbol: str | None = None,
        start: datetime | str | None = None,
        end: datetime | str | None = None,
        tag: str | None = None,
        strategy: str | None = None,
    ) -> PaginatedOrders:
        """Return a slice of the orders log with optional filters applied."""

        params: dict[str, object] = {"limit": limit, "offset": offset}
        if account_id:
            params["account_id"] = account_id
        if symbol:
            params["symbol"] = symbol
        if start:
            params["start"] = start.isoformat() if isinstance(start, datetime) else start
        if end:
            params["end"] = end.isoformat() if isinstance(end, datetime) else end
        if tag:
            params["tag"] = tag
        if strategy:
            params["strategy"] = strategy

        response = self._client.get(
            "/orders/log",
            params=params,
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

    def annotate_order(self, order_id: int, *, notes: str, tags: list[str] | None = None) -> OrderRecord:
        payload: dict[str, object] = {"notes": notes}
        if tags:
            payload["tags"] = tags
        response = self._client.post(
            f"/orders/{order_id}/notes",
            json=payload,
            headers={"accept": "application/json"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise exc
        try:
            body = response.json()
        except ValueError as exc:
            raise OrderRouterError(
                "Order router returned non JSON payload", response=response
            ) from exc
        try:
            return OrderRecord.model_validate(body)
        except ValidationError as exc:
            raise OrderRouterError("Unable to parse order router payload", response=response) from exc


    def fetch_positions(self) -> PositionsResponse:
        """Return the current positions snapshot exposed by the order router."""

        response = self._client.get(
            "/positions",
            headers={"accept": "application/json"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise OrderRouterError(
                "Order router returned non JSON payload", response=response
            ) from exc
        try:
            return PositionsResponse.model_validate(payload)
        except ValidationError as exc:
            raise OrderRouterError("Unable to parse order router payload", response=response) from exc


    def close_position(
        self, position_id: str, *, target_quantity: float | None = None
    ) -> PositionCloseResponse:
        """Request a close or adjustment for an existing position."""

        request_model = PositionCloseRequest(target_quantity=target_quantity)
        body = request_model.model_dump(exclude_none=True)
        response = self._client.post(
            f"/positions/{position_id}/close",
            json=body,
            headers={"accept": "application/json"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise OrderRouterError(
                "Order router returned non JSON payload", response=response
            ) from exc
        try:
            return PositionCloseResponse.model_validate(payload)
        except ValidationError as exc:
            raise OrderRouterError("Unable to parse order router payload", response=response) from exc


__all__ = ["OrderRouterClient", "OrderRouterError"]
