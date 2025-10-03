"""Integration tests for market connectors using docker-style fixtures."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from libs.connectors import MarketConnector
from services.market_data.adapters import BinanceMarketConnector, IBKRMarketConnector


@dataclass
class MockDockerService:
    """Utility representing a dockerised dependency for integration tests."""

    name: str
    startup_delay: float = 0.0

    async def ready(self) -> None:
        await asyncio.sleep(self.startup_delay)


class DockerisedBinanceRestClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def klines(self, *, symbol: str, interval: str, limit: int) -> list[list[Any]]:
        self.calls.append({"symbol": symbol, "interval": interval, "limit": limit})
        return [[1_000, "1", "2", "0.5", "1.5", "10", 1_060, "100", 5]]


class DockerisedBinanceStream:
    def __init__(
        self,
        *,
        on_message: Callable[..., None],
        on_close: Callable[..., None],
        on_error: Callable[..., None],
        responses: Iterable[str],
        error_on_first: bool,
        **_: Any,
    ) -> None:
        self._on_message = on_message
        self._on_close = on_close
        self._on_error = on_error
        self._responses = list(responses)
        self._error_on_first = error_on_first
        self.subscriptions: list[str] = []

    def subscribe(self, stream: str) -> None:
        self.subscriptions.append(stream)
        for index, payload in enumerate(self._responses):
            self._on_message(json.dumps({"p": payload, "s": stream.split("@")[0].upper()}))
            if self._error_on_first and index == 0:
                self._on_error(ConnectionError("transient"))
                return
        self._on_close()

    def stop(self) -> None:  # pragma: no cover - no resources to release in tests
        return None


async def _binance_docker_clients() -> dict[str, Any]:
    service = MockDockerService(name="binance", startup_delay=0.01)
    await service.ready()
    call_count = {"value": 0}

    return {
        "rest_client": DockerisedBinanceRestClient(),
        "websocket_client_factory": lambda **kwargs: _binance_stream_factory(call_count, **kwargs),
    }


def _binance_stream_factory(call_count: dict[str, int], **kwargs: Any) -> DockerisedBinanceStream:
    call_count["value"] += 1
    if call_count["value"] == 1:
        return DockerisedBinanceStream(
            responses=["42000"],
            error_on_first=True,
            **kwargs,
        )
    return DockerisedBinanceStream(responses=["42001"], error_on_first=False, **kwargs)


class DockerisedIBKR:
    MaxRequests = 10
    RequestsInterval = 0.5

    def __init__(self) -> None:
        self.connected = False
        self.pendingTickersEvent = _TickerEvent()
        self.reqHistoricalData_calls: list[dict[str, Any]] = []
        self.reqMktData_calls = 0

    async def connectAsync(self, host: str, port: int, clientId: int) -> None:  # noqa: N802
        self.connected = True
        await asyncio.sleep(0)

    def isConnected(self) -> bool:  # noqa: N802
        return self.connected

    async def reqHistoricalDataAsync(self, contract: Any, **kwargs: Any) -> list[str]:
        self.reqHistoricalData_calls.append({"contract": contract, **kwargs})
        return ["bar"]

    def reqMktData(self, contract: Any, *args: Any, **kwargs: Any) -> None:  # noqa: N802
        self.reqMktData_calls += 1
        if self.reqMktData_calls == 1:
            raise ConnectionError("socket closed")
        self.pendingTickersEvent.add_sequence(
            [type("Ticker", (), {"contract": contract, "last": 10.0})]
        )

    def cancelMktData(self, contract: Any) -> None:  # noqa: N802
        return None

    def disconnect(self) -> None:
        self.connected = False


class _TickerEvent:
    def __init__(self) -> None:
        self._sequences: list[Iterable[Any]] = []

    def add_sequence(self, sequence: Iterable[Any]) -> None:
        self._sequences.append(sequence)

    async def aiter(self) -> AsyncIterator[Iterable[Any]]:
        for sequence in list(self._sequences):
            yield sequence
        await asyncio.sleep(0)


async def _ibkr_docker_client() -> DockerisedIBKR:
    service = MockDockerService(name="ibkr", startup_delay=0.01)
    await service.ready()
    return DockerisedIBKR()


def test_binance_connector_end_to_end() -> None:
    async def run() -> None:
        connector: MarketConnector = BinanceMarketConnector(
            **(await _binance_docker_clients()), request_rate=1, request_interval_seconds=0.2
        )
        first = asyncio.get_running_loop().time()
        await connector.fetch_ohlcv("BTCUSDT", "1m")
        second = asyncio.get_running_loop().time()
        await connector.fetch_ohlcv("BTCUSDT", "1m")
        assert second - first < 0.05
        third = asyncio.get_running_loop().time()
        await connector.fetch_ohlcv("BTCUSDT", "1m")
        assert third - second >= 0.18

        stream = connector.stream_trades("BTCUSDT")
        messages = []
        async for message in stream:
            messages.append(message)
            if len(messages) == 2:
                break
        await stream.aclose()
        assert [msg["p"] for msg in messages] == ["42000", "42001"]

    asyncio.run(run())


def test_ibkr_connector_retries_with_docker_fixture() -> None:
    async def run() -> None:
        ibkr_docker = await _ibkr_docker_client()
        connector: MarketConnector = IBKRMarketConnector(
            host="127.0.0.1",
            port=4001,
            client_id=1,
            ib=ibkr_docker,
            reconnect_delay=0.01,
        )

        await connector.fetch_ohlcv("ES", end="", duration="1 D", bar_size="1 min")
        await connector.fetch_ohlcv("ES", end="", duration="1 D", bar_size="1 min")
        assert len(ibkr_docker.reqHistoricalData_calls) == 2

        stream = connector.stream_trades("ES")
        ticker = await stream.__anext__()
        await stream.aclose()
        assert ibkr_docker.reqMktData_calls >= 2
        assert getattr(ticker, "last", None) == 10.0

    asyncio.run(run())
