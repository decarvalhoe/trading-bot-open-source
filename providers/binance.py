"""Binance REST client with request signing and rate limiting helpers."""
from __future__ import annotations

import hashlib
import hmac
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Mapping, MutableMapping

import httpx


def normalize_symbol(symbol: str) -> str:
    """Normalise Binance trading symbols.

    Binance expects uppercase symbols without separators. The helper accepts
    common input formats such as ``BTC/USDT`` or ``eth-usdt`` and returns the
    canonical representation used by both the REST and websocket APIs.
    """

    return symbol.replace("/", "").replace("-", "").strip().upper()


class SlidingWindowRateLimiter:
    """Thread-safe rate limiter relying on a sliding time window."""

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
class BinanceConfig:
    """Configuration values required by :class:`BinanceClient`."""

    api_key: str | None
    api_secret: str | None
    base_url: str = "https://api.binance.com"
    recv_window: int = 5_000
    timeout: float = 10.0
    request_rate: int = 1_200
    request_interval: float = 60.0


class BinanceError(RuntimeError):
    """Raised when the Binance API responds with an error."""


class BinanceClient:
    """Lightweight synchronous client for the Binance REST API."""

    def __init__(
        self,
        config: BinanceConfig,
        *,
        client: httpx.Client | None = None,
        rate_limiter: SlidingWindowRateLimiter | None = None,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
    ) -> None:
        self._config = config
        self._max_retries = max(1, max_retries)
        self._backoff_factor = max(0.0, backoff_factor)
        headers: dict[str, str] = {}
        if config.api_key:
            headers["X-MBX-APIKEY"] = config.api_key
        self._client = client or httpx.Client(
            base_url=config.base_url.rstrip("/"),
            timeout=config.timeout,
            headers=headers,
        )
        self._rate_limiter = rate_limiter or SlidingWindowRateLimiter(
            config.request_rate, config.request_interval
        )

    def close(self) -> None:
        self._client.close()

    def _sign_payload(self, params: Mapping[str, Any]) -> str:
        if not self._config.api_secret:
            raise BinanceError("API secret is required for signed endpoints")
        query = "&".join(
            f"{key}={value}" for key, value in sorted(params.items()) if value is not None
        )
        signature = hmac.new(
            self._config.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature

    def _prepare_signed_params(self, params: MutableMapping[str, Any]) -> None:
        params["timestamp"] = int(time.time() * 1_000)
        params["recvWindow"] = self._config.recv_window
        params["signature"] = self._sign_payload(params)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: MutableMapping[str, Any] | None = None,
        signed: bool = False,
    ) -> Dict[str, Any]:
        base_payload: MutableMapping[str, Any] = dict(params or {})
        attempt = 1
        backoff = self._backoff_factor
        while True:
            payload: Dict[str, Any] = dict(base_payload)
            if signed:
                self._prepare_signed_params(payload)
            self._rate_limiter.acquire()
            try:
                response = self._client.request(method, path, params=payload)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if status_code >= 500 and attempt < self._max_retries:
                    time.sleep(backoff)
                    attempt += 1
                    backoff *= 2 or 1  # ensure exponential growth even when factor is 0
                    continue
                raise BinanceError(f"Binance API error ({status_code})") from exc
            except httpx.HTTPError as exc:
                if attempt < self._max_retries:
                    time.sleep(backoff)
                    attempt += 1
                    backoff *= 2 or 1
                    continue
                raise BinanceError("Failed to reach Binance API") from exc
            try:
                return response.json()
            except ValueError as exc:  # pragma: no cover - defensive guard
                raise BinanceError("Invalid JSON payload returned by Binance") from exc

    def place_order(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        time_in_force: str | None = None,
        extra_params: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "symbol": normalize_symbol(symbol),
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": quantity,
        }
        if price is not None:
            payload["price"] = price
        if time_in_force:
            payload["timeInForce"] = time_in_force
        if extra_params:
            payload.update(extra_params)
        return self._request("POST", "/api/v3/order", params=payload, signed=True)

    def cancel_order(
        self,
        *,
        symbol: str,
        order_id: str,
        extra_params: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "symbol": normalize_symbol(symbol),
            "orderId": order_id,
        }
        if extra_params:
            payload.update(extra_params)
        return self._request("DELETE", "/api/v3/order", params=payload, signed=True)


__all__ = ["BinanceClient", "BinanceConfig", "BinanceError", "normalize_symbol"]
