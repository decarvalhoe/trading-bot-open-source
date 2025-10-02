"""Interactive Brokers HTTP client with automatic session management."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Mapping, MutableMapping

import httpx


def normalize_symbol(symbol: str) -> str:
    """Normalise IBKR symbols by stripping separators and upper-casing."""

    return symbol.replace("/", "").replace("-", "").replace(" ", "").upper()


class SlidingWindowRateLimiter:
    """Rate limiter with a sliding window suited for synchronous workflows."""

    def __init__(self, rate: int, per_seconds: float) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        if per_seconds <= 0:
            raise ValueError("per_seconds must be positive")
        self._rate = rate
        self._per_seconds = per_seconds
        self._lock = threading.Lock()
        self._timestamps: list[float] = []

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                self._timestamps = [
                    ts for ts in self._timestamps if now - ts < self._per_seconds
                ]
                if len(self._timestamps) < self._rate:
                    self._timestamps.append(now)
                    return
                sleep_for = self._per_seconds - (now - self._timestamps[0])
            if sleep_for > 0:
                time.sleep(sleep_for)


@dataclass(slots=True)
class IBKRConfig:
    """Configuration for :class:`IBKRClient`."""

    api_key: str | None
    api_secret: str | None
    base_url: str = "https://localhost:5000"
    account_id: str | None = None
    timeout: float = 10.0
    request_rate: int = 60
    request_interval: float = 60.0


class IBKRError(RuntimeError):
    """Raised when the IBKR gateway responds with an error."""


class IBKRClient:
    """Minimal synchronous client wrapping the IBKR Web API."""

    def __init__(
        self,
        config: IBKRConfig,
        *,
        client: httpx.Client | None = None,
        rate_limiter: SlidingWindowRateLimiter | None = None,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
    ) -> None:
        self._config = config
        self._client = client or httpx.Client(
            base_url=config.base_url.rstrip("/"), timeout=config.timeout
        )
        self._rate_limiter = rate_limiter or SlidingWindowRateLimiter(
            config.request_rate, config.request_interval
        )
        self._max_retries = max(1, max_retries)
        self._backoff_factor = max(0.0, backoff_factor)
        self._session_token: str | None = None
        self._lock = threading.RLock()

    def close(self) -> None:
        self._client.close()

    def _login(self) -> None:
        if not self._config.api_key or not self._config.api_secret:
            raise IBKRError("API key and secret are required to authenticate with IBKR")
        response = self._client.post(
            "/session",
            json={"apiKey": self._config.api_key, "apiSecret": self._config.api_secret},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:  # pragma: no cover - defensive guard
            raise IBKRError("Failed to authenticate with IBKR") from exc
        payload = response.json()
        token = payload.get("session") if isinstance(payload, dict) else None
        if not token:
            raise IBKRError("IBKR authentication did not return a session token")
        self._session_token = str(token)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        params: MutableMapping[str, Any] | None = None,
        requires_auth: bool = True,
    ) -> Dict[str, Any]:
        attempt = 1
        backoff = self._backoff_factor
        while True:
            self._rate_limiter.acquire()
            headers: dict[str, str] = {}
            if requires_auth:
                with self._lock:
                    if not self._session_token:
                        self._login()
                    headers["Authorization"] = f"Bearer {self._session_token}"  # type: ignore[str-format]
            try:
                response = self._client.request(
                    method,
                    path,
                    json=json,
                    params=params,
                    headers=headers if headers else None,
                )
                if response.status_code == 401 and requires_auth:
                    with self._lock:
                        self._session_token = None
                    if attempt < self._max_retries:
                        self._login()
                        attempt += 1
                        continue
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if status_code >= 500 and attempt < self._max_retries:
                    time.sleep(backoff)
                    attempt += 1
                    backoff *= 2 or 1
                    continue
                raise IBKRError(f"IBKR API error ({status_code})") from exc
            except httpx.HTTPError as exc:
                if attempt < self._max_retries:
                    time.sleep(backoff)
                    attempt += 1
                    backoff *= 2 or 1
                    continue
                raise IBKRError("Failed to reach IBKR API") from exc
            try:
                payload = response.json()
            except ValueError as exc:  # pragma: no cover - defensive guard
                raise IBKRError("Invalid JSON payload returned by IBKR") from exc
            if isinstance(payload, dict):
                return payload
            return {"data": payload}

    def place_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str,
        price: float | None = None,
        time_in_force: str | None = None,
        account_id: str | None = None,
        extra_params: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        account = account_id or self._config.account_id
        if not account:
            raise IBKRError("An account identifier is required to place orders")
        payload: Dict[str, Any] = {
            "symbol": normalize_symbol(symbol),
            "side": side.upper(),
            "orderType": order_type.upper(),
            "quantity": quantity,
        }
        if price is not None:
            payload["price"] = price
        if time_in_force:
            payload["timeInForce"] = time_in_force
        if extra_params:
            payload.update(extra_params)
        return self._request(
            "POST",
            f"/iserver/account/{account}/order",
            json=payload,
        )

    def cancel_order(
        self,
        *,
        account_id: str | None,
        order_id: str,
    ) -> Dict[str, Any]:
        account = account_id or self._config.account_id
        if not account:
            raise IBKRError("An account identifier is required to cancel orders")
        return self._request(
            "DELETE",
            f"/iserver/account/{account}/order/{order_id}",
            requires_auth=True,
            json=None,
            params=None,
        )


__all__ = ["IBKRClient", "IBKRConfig", "IBKRError", "normalize_symbol"]
