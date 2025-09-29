"""Broker adapter abstractions for the order router."""
from __future__ import annotations

import abc
from typing import Dict, Iterable, List

from libs.connectors import ExecutionClient
from schemas.market import ExecutionStatus, OrderRequest
from schemas.order_router import ExecutionReport


class BrokerAdapter(ExecutionClient, abc.ABC):
    """Abstract broker adapter."""

    name: str

    def __init__(self) -> None:
        self._reports: Dict[str, ExecutionReport] = {}

    @abc.abstractmethod
    def place_order(self, order: OrderRequest, *, reference_price: float) -> ExecutionReport:
        """Submit an order to the remote broker."""

    def cancel_order(self, order_id: str) -> ExecutionReport:
        try:
            report = self._reports[order_id]
        except KeyError as exc:  # pragma: no cover - defensive branch
            raise KeyError("Unknown order") from exc
        cancelled = report.model_copy(update={"status": ExecutionStatus.CANCELLED})
        self._reports[order_id] = cancelled
        return cancelled

    def fetch_executions(self) -> Iterable[ExecutionReport]:
        return [
            report
            for report in self._reports.values()
            if report.status in {ExecutionStatus.FILLED, ExecutionStatus.PARTIALLY_FILLED}
        ]

    def _store_report(self, report: ExecutionReport) -> ExecutionReport:
        self._reports[report.order_id] = report
        return report

    def reports(self) -> List[ExecutionReport]:
        return list(self._reports.values())


__all__ = ["BrokerAdapter"]
