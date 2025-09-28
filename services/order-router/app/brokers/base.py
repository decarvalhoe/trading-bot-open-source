"""Broker adapter abstractions for the order router."""
from __future__ import annotations

import abc
from typing import Dict, List


class BrokerAdapter(abc.ABC):
    """Abstract broker adapter."""

    name: str

    def __init__(self) -> None:
        self.orders: List[Dict[str, float]] = []
        self.executions: List[Dict[str, float]] = []

    @abc.abstractmethod
    def place_order(self, order: Dict[str, float]) -> Dict[str, float]:
        """Submit an order to the remote broker."""

    def cancel_order(self, order_id: str) -> Dict[str, str]:
        return {"order_id": order_id, "status": "cancelled"}

    def fetch_executions(self) -> List[Dict[str, float]]:
        return list(self.executions)


__all__ = ["BrokerAdapter"]
