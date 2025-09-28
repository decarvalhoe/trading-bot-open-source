"""Common connector interfaces for market data and execution clients."""
from __future__ import annotations

import abc
from typing import Any, AsyncIterator, Iterable


class MarketConnector(abc.ABC):
    """Abstract base class for market data providers.

    The interface intentionally keeps the contract minimal so that concrete
    implementations can expose vendor specific keyword arguments when
    necessary. Implementations are expected to honour rate limiting and retry
    semantics internally when interacting with upstream APIs.
    """

    @abc.abstractmethod
    async def fetch_ohlcv(self, instrument: Any, **kwargs: Any) -> Iterable[Any]:
        """Retrieve OHLCV bars for the requested instrument."""

    @abc.abstractmethod
    async def stream_trades(self, instrument: Any, **kwargs: Any) -> AsyncIterator[Any]:
        """Yield trades/ticks for the requested instrument."""


class ExecutionClient(abc.ABC):
    """Abstract base class for order execution clients."""

    name: str

    @abc.abstractmethod
    def place_order(self, order: Any, **kwargs: Any) -> Any:
        """Submit an order to the remote venue."""

    @abc.abstractmethod
    def cancel_order(self, order_id: str) -> Any:
        """Cancel an order that was previously submitted."""

    @abc.abstractmethod
    def fetch_executions(self) -> Iterable[Any]:
        """Fetch execution reports from the remote venue."""
