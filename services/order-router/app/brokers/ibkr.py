"""Interactive Brokers adapter."""
from __future__ import annotations

from typing import Dict

from .base import BrokerAdapter


class IBKRAdapter(BrokerAdapter):
    name = "ibkr"

    def place_order(self, order: Dict[str, float]) -> Dict[str, float]:
        order_id = f"IB-{len(self.orders) + 1}"
        enriched = {**order, "order_id": order_id, "status": "accepted"}
        self.orders.append(enriched)
        if order.get("quantity", 0) != 0:
            execution = {
                "order_id": order_id,
                "filled_qty": order["quantity"] * 0.95,
                "price": order.get("price", 0.0),
            }
            self.executions.append(execution)
        return enriched


__all__ = ["IBKRAdapter"]
