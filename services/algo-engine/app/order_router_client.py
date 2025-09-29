"""Async client used by the algo engine to reach the order router service."""
from __future__ import annotations

import os
from typing import Any

import httpx

from schemas.order_router import ExecutionIntent, ExecutionReport


class OrderRouterClientError(RuntimeError):
    """Raised when the order router service cannot process a request."""


class OrderRouterClient:
    """HTTP client responsible for submitting intents to the order router."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        env_base_url = os.getenv("ORDER_ROUTER_URL", "http://order-router:8000")
        env_timeout = os.getenv("ORDER_ROUTER_TIMEOUT", "5.0")
        env_api_key = os.getenv("ORDER_ROUTER_API_KEY")

        self._base_url = (base_url or env_base_url).rstrip("/")
        try:
            self._timeout = float(timeout if timeout is not None else env_timeout)
        except ValueError as exc:  # pragma: no cover - defensive validation
            raise OrderRouterClientError("ORDER_ROUTER_TIMEOUT must be a number") from exc
        self._api_key = api_key if api_key is not None else env_api_key
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers: dict[str, str] = {}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                headers=headers,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def submit_order(self, intent: ExecutionIntent) -> ExecutionReport:
        """Submit an :class:`ExecutionIntent` to the router and parse the report."""

        payload = intent.model_dump(mode="json", exclude_none=True)
        client = await self._get_client()
        try:
            response = await client.post("/orders", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            message = self._extract_error_message(exc.response)
            raise OrderRouterClientError(
                f"order router responded with {exc.response.status_code}: {message}"
            ) from exc
        except httpx.RequestError as exc:
            raise OrderRouterClientError(f"failed to contact order router: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:  # pragma: no cover - response contract violation
            raise OrderRouterClientError("invalid JSON payload returned by order router") from exc

        try:
            return ExecutionReport.model_validate(data)
        except Exception as exc:  # pragma: no cover - schema validation safety net
            raise OrderRouterClientError("unable to parse execution report") from exc

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str:
        try:
            payload: Any = response.json()
        except ValueError:
            return response.text

        if isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, str):
                return detail
        return response.text

    async def __aenter__(self) -> "OrderRouterClient":
        await self._get_client()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()


__all__ = ["OrderRouterClient", "OrderRouterClientError"]
