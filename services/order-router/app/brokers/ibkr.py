"""Paper IBKR broker adapter used by the sandbox order router."""
from __future__ import annotations

from datetime import datetime, timezone

from schemas.market import ExecutionFill, ExecutionReport, ExecutionStatus, OrderRequest

from .base import BrokerAdapter


class IBKRAdapter(BrokerAdapter):
    name = "ibkr"

    def place_order(self, order: OrderRequest, *, reference_price: float) -> ExecutionReport:
        order_id = f"IB-{len(self.reports()) + 1}"
        fill_price = reference_price if reference_price > 0 else 1.0
        filled_quantity = order.quantity * 0.95
        fill = ExecutionFill(
            quantity=filled_quantity,
            price=fill_price,
            timestamp=datetime.now(timezone.utc),
        )
        status = ExecutionStatus.PARTIALLY_FILLED if filled_quantity < order.quantity else ExecutionStatus.FILLED
        report = ExecutionReport(
            order_id=order_id,
            status=status,
            broker=self.name,
            venue=order.venue,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            filled_quantity=filled_quantity,
            avg_price=fill_price,
            submitted_at=datetime.now(timezone.utc),
            fills=[fill],
            tags=order.tags,
        )
        return self._store_report(report)


__all__ = ["IBKRAdapter"]
