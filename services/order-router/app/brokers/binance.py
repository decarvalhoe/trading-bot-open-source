"""Sandbox Binance adapter returning deterministic execution reports."""
from __future__ import annotations

from datetime import datetime, timezone

from schemas.market import ExecutionFill, ExecutionReport, ExecutionStatus, OrderRequest

from .base import BrokerAdapter


class BinanceAdapter(BrokerAdapter):
    name = "binance"

    def place_order(self, order: OrderRequest, *, reference_price: float) -> ExecutionReport:
        price = reference_price if reference_price > 0 else 1.0
        order_id = f"BN-{len(self.reports()) + 1}"
        fill = ExecutionFill(
            quantity=order.quantity,
            price=price,
            timestamp=datetime.now(timezone.utc),
        )
        report = ExecutionReport(
            order_id=order_id,
            status=ExecutionStatus.FILLED,
            broker=self.name,
            venue=order.venue,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            filled_quantity=order.quantity,
            avg_price=price,
            submitted_at=datetime.now(timezone.utc),
            fills=[fill],
            tags=order.tags,
        )
        return self._store_report(report)


__all__ = ["BinanceAdapter"]
