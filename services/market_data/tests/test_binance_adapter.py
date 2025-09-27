from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, Callable

import pytest

from services.market_data.adapters import BinanceMarketDataAdapter


class FakeSpotClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def klines(self, *, symbol: str, interval: str, limit: int) -> list[list[Any]]:
        self.calls.append({"symbol": symbol, "interval": interval, "limit": limit})
        return [[1_000, "1", "2", "0.5", "1.5", "10", 1_060, "100", 5]]


class FakeWebsocketClient:
    def __init__(
        self,
        *,
        on_message: Callable[..., None],
        on_close: Callable[..., None],
        on_error: Callable[..., None],
        sequence: int,
        **_: Any,
    ) -> None:
        self._on_message = on_message
        self._on_close = on_close
        self._on_error = on_error
        self._sequence = sequence
        self.subscriptions: list[str] = []

    def subscribe(self, stream: str) -> None:
        self.subscriptions.append(stream)
        if self._sequence == 1:
            payload = json.dumps({"s": "BTCUSDT", "p": "42000"})
            self._on_message(payload)
            self._on_error(ConnectionError("boom"))
        else:
            payload = json.dumps({"s": "BTCUSDT", "p": "42001"})
            self._on_message(payload)
            self._on_close()

    def stop(self) -> None:  # pragma: no cover - nothing to clean up for the fake
        return None


@pytest.mark.asyncio
async def test_binance_fetch_respects_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSpotClient()
    counter = {"value": 0}

    def factory(**kwargs: Any) -> FakeWebsocketClient:
        counter["value"] += 1
        return FakeWebsocketClient(sequence=counter["value"], **kwargs)

    adapter = BinanceMarketDataAdapter(
        rest_client=fake,
        websocket_client_factory=factory,
        request_rate=1,
        request_interval_seconds=0.2,
    )

    first = asyncio.get_running_loop().time()
    await adapter.fetch_ohlcv("BTCUSDT", "1m")
    second = asyncio.get_running_loop().time()
    await adapter.fetch_ohlcv("BTCUSDT", "1m")
    third = asyncio.get_running_loop().time()

    assert third - second >= 0.18
    assert fake.calls[0]["symbol"] == "BTCUSDT"


@pytest.mark.asyncio
async def test_binance_stream_reconnects(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = {"value": 0}

    def factory(**kwargs: Any) -> FakeWebsocketClient:
        counter["value"] += 1
        return FakeWebsocketClient(sequence=counter["value"], **kwargs)

    adapter = BinanceMarketDataAdapter(
        rest_client=FakeSpotClient(),
        websocket_client_factory=factory,
        reconnect_delay=0.01,
    )

    async def take_two(stream: AsyncIterator[dict[str, Any]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        async for message in stream:
            items.append(message)
            if len(items) == 2:
                break
        return items

    stream = adapter.stream_trades("BTCUSDT")
    items = await take_two(stream)
    await stream.aclose()

    assert [item["p"] for item in items] == ["42000", "42001"]
