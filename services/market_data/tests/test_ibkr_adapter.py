from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Iterable

import pytest

from services.market_data.adapters import IBKRMarketDataAdapter


class FakeEvent:
    def __init__(self) -> None:
        self._sequences: list[Iterable[Any]] = []

    def add_sequence(self, sequence: Iterable[Any]) -> None:
        self._sequences.append(sequence)

    async def aiter(self):  # type: ignore[override]
        for sequence in list(self._sequences):
            yield sequence
        await asyncio.sleep(0)


class FakeIB:
    MaxRequests = 10
    RequestsInterval = 1.0

    def __init__(self) -> None:
        self.connected = False
        self.pendingTickersEvent = FakeEvent()
        self.reqMktData_calls = 0
        self.reqHistoricalData_calls: list[dict[str, Any]] = []

    async def connectAsync(self, host: str, port: int, clientId: int) -> None:  # noqa: N802
        self.connected = True

    def isConnected(self) -> bool:  # noqa: N802
        return self.connected

    def disconnect(self) -> None:
        self.connected = False

    async def reqHistoricalDataAsync(self, contract: Any, **kwargs: Any) -> list[str]:
        self.reqHistoricalData_calls.append({"contract": contract, **kwargs})
        return ["bar"]

    def reqMktData(self, contract: Any, *args: Any, **kwargs: Any) -> None:  # noqa: N802
        self.reqMktData_calls += 1
        if self.reqMktData_calls == 1:
            raise ConnectionError("disconnected")
        self.pendingTickersEvent.add_sequence([
            type("Ticker", (), {"contract": contract, "last": 10.0, "time": kwargs.get("time", None)})
        ])

    def cancelMktData(self, contract: Any) -> None:  # noqa: N802
        return None


@pytest.mark.asyncio
async def test_ibkr_fetch_uses_rate_limit() -> None:
    fake_ib = FakeIB()
    adapter = IBKRMarketDataAdapter(host="127.0.0.1", port=4001, client_id=1, ib=fake_ib, request_rate=1, request_interval_seconds=0.2)

    await adapter.fetch_ohlcv("ES", end="", duration="1 D", bar_size="1 min")
    await adapter.fetch_ohlcv("ES", end="", duration="1 D", bar_size="1 min")

    assert len(fake_ib.reqHistoricalData_calls) == 2


@pytest.mark.asyncio
async def test_ibkr_stream_reconnects() -> None:
    fake_ib = FakeIB()
    adapter = IBKRMarketDataAdapter(host="127.0.0.1", port=4001, client_id=1, ib=fake_ib, reconnect_delay=0.01)

    async def collect(stream: AsyncIterator[Any]) -> list[Any]:
        items: list[Any] = []
        async for ticker in stream:
            items.append(ticker)
            if len(items) == 1:
                break
        return items

    stream = adapter.stream_ticks("ES")
    items = await collect(stream)
    await stream.aclose()

    assert fake_ib.reqMktData_calls == 2
    assert items[0].last == 10.0
