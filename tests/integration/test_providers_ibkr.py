from __future__ import annotations

import asyncio
import os
import time
from typing import Any, AsyncIterator, Iterable

import httpx
import pytest
from httpx import Response

from services.market_data.adapters import IBKRMarketConnector

_IBKR_BASE_URL = os.environ.get("IBKR_HTTP_SANDBOX_URL", "https://ibkr.test")


class _TickerEvent:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[Iterable[Any]] = asyncio.Queue()

    def add_sequence(self, sequence: Iterable[Any]) -> None:
        self._queue.put_nowait(sequence)

    async def aiter(self) -> AsyncIterator[Iterable[Any]]:  # type: ignore[override]
        while True:
            sequence = await self._queue.get()
            yield sequence


class _HttpIBGateway:
    MaxRequests = 5
    RequestsInterval = 0.2

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base_url)
        self.connected = False
        self.pendingTickersEvent = _TickerEvent()
        self.reqHistoricalData_calls: list[dict[str, Any]] = []
        self.reqMktData_calls = 0

    async def connectAsync(self, host: str, port: int, clientId: int) -> None:  # noqa: N802
        self.connected = True
        await asyncio.sleep(0)

    def isConnected(self) -> bool:  # noqa: N802
        return self.connected

    async def reqHistoricalDataAsync(self, contract: Any, **kwargs: Any) -> list[dict[str, Any]]:
        response = await self._client.get("/historical", params={"contract": contract})
        response.raise_for_status()
        payload = response.json()
        self.reqHistoricalData_calls.append({"contract": contract, **kwargs})
        return list(payload.get("bars", []))

    def reqMktData(self, contract: Any, *args: Any, **kwargs: Any) -> None:  # noqa: N802
        self.reqMktData_calls += 1
        if self.reqMktData_calls == 1:
            raise ConnectionError("gateway warmup")
        asyncio.create_task(self._populate_ticks(contract))

    async def _populate_ticks(self, contract: Any) -> None:
        try:
            response = await self._client.get("/stream", params={"contract": contract})
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise ConnectionError("stream failure") from exc
        ticks = [
            type("Ticker", (), {"contract": contract, "last": item["last"], "time": item["time"]})
            for item in payload.get("ticks", [])
        ]
        self.pendingTickersEvent.add_sequence(ticks)

    def cancelMktData(self, contract: Any) -> None:  # noqa: N802
        return None

    def disconnect(self) -> None:
        self.connected = False

    async def aclose(self) -> None:
        await self._client.aclose()


@pytest.mark.asyncio
async def test_ibkr_provider_latency_and_reconnect(
    sandbox_mode: str, sandbox_respx: Any
) -> None:
    """Ensure the IBKR connector handles pacing and reconnects."""

    if sandbox_mode != "sandbox":
        pytest.skip("IBKR official gateway requires dedicated infrastructure")

    assert sandbox_respx is not None

    gateway = _HttpIBGateway(_IBKR_BASE_URL)
    connector = IBKRMarketConnector(
        host="127.0.0.1",
        port=4001,
        client_id=1,
        ib=gateway,
        request_rate=1,
        request_interval_seconds=0.2,
        reconnect_delay=0.01,
    )

    async def _historical_handler(request: httpx.Request) -> Response:
        await asyncio.sleep(0.05)
        return Response(200, json={"bars": [{"close": 100.0, "open": 99.5}]})

    async def _stream_handler(request: httpx.Request) -> Response:
        await asyncio.sleep(0.01)
        return Response(
            200,
            json={"ticks": [{"last": 101.0, "time": "2024-01-01T00:00:00Z"}]},
        )

    sandbox_respx.get(f"{_IBKR_BASE_URL}/historical").mock(side_effect=_historical_handler)
    sandbox_respx.get(f"{_IBKR_BASE_URL}/stream").mock(side_effect=_stream_handler)

    start = time.perf_counter()
    bars_first = await connector.fetch_ohlcv("ES", end="", duration="1 D", bar_size="1 min")
    middle = time.perf_counter()
    bars_second = await connector.fetch_ohlcv("ES", end="", duration="1 D", bar_size="1 min")
    end = time.perf_counter()

    assert bars_first and bars_second
    assert bars_first[0]["close"] == pytest.approx(100.0)
    assert end - middle >= 0.18
    assert middle - start >= 0.05

    stream = connector.stream_trades("ES")
    ticker = await stream.__anext__()
    await stream.aclose()

    assert gateway.reqMktData_calls >= 2
    assert getattr(ticker, "last", None) == pytest.approx(101.0)

    await gateway.aclose()
