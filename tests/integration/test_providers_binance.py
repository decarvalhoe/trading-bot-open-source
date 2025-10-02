from __future__ import annotations

import os
import time
from typing import Any

import pytest
import httpx
from httpx import Response

from services.market_data.adapters import BinanceMarketConnector

BINANCE_BASE_URL = os.environ.get("BINANCE_API_BASE_URL", "https://api.binance.com")


class _HttpxSpotClient:
    def __init__(self, base_url: str) -> None:
        self._client = httpx.Client(base_url=base_url)

    def klines(self, *, symbol: str, interval: str, limit: int) -> list[list[str | float | int]]:
        response = self._client.get(
            "/api/v3/klines", params={"symbol": symbol, "interval": interval, "limit": limit}
        )
        response.raise_for_status()
        payload = response.json()
        return payload  # type: ignore[return-value]

    def close(self) -> None:
        self._client.close()


@pytest.mark.asyncio
async def test_binance_provider_latency_and_resilience(
    sandbox_mode: str, sandbox_respx: Any
) -> None:
    """Ensure the Binance connector tolerates latency and transient failures."""

    rest_client = _HttpxSpotClient(BINANCE_BASE_URL)
    adapter = BinanceMarketConnector(
        rest_client=rest_client,
        api_key=os.environ.get("BINANCE_API_KEY"),
        api_secret=os.environ.get("BINANCE_API_SECRET"),
        request_rate=1,
        request_interval_seconds=0.2,
    )

    try:
        if sandbox_mode == "sandbox":
            call_count = {"value": 0}

            assert sandbox_respx is not None

            def _mock_response(request: Any) -> Response:
                call_count["value"] += 1
                attempt = call_count["value"]
                if attempt == 1:
                    time.sleep(0.05)
                    return Response(500, json={"code": -1000, "msg": "internal error"})
                time.sleep(0.01)
                return Response(
                    200,
                    json=[[1_000, "1", "2", "0.5", "1.5", "10", 1_060, "100", 5]],
                )

            sandbox_respx.get(f"{BINANCE_BASE_URL}/api/v3/klines").mock(side_effect=_mock_response)

            start = time.perf_counter()
            with pytest.raises(Exception):
                await adapter.fetch_ohlcv("BTCUSDT", "1m", limit=1)
            between = time.perf_counter()
            candles = await adapter.fetch_ohlcv("BTCUSDT", "1m", limit=1)
            end = time.perf_counter()

            assert call_count["value"] == 2
        else:
            try:
                start = time.perf_counter()
                await adapter.fetch_ohlcv("BTCUSDT", "1m", limit=1)
                between = time.perf_counter()
                candles = await adapter.fetch_ohlcv("BTCUSDT", "1m", limit=1)
                end = time.perf_counter()
            except Exception as exc:  # pragma: no cover - live environment failure
                pytest.skip(f"Binance live environment unavailable: {exc}")

        assert candles, "Connector should return at least one candle"
        if sandbox_mode == "sandbox":
            assert candles[0]["close"] == 1.5
        else:
            assert "close" in candles[0]
        assert end - between >= 0.15
        if sandbox_mode == "sandbox":
            assert between - start >= 0.05
    finally:
        rest_client.close()
