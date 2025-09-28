"""Risk management primitives for the order router."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Protocol

from schemas.market import OrderRequest


class RiskRule(Protocol):
    """Protocol describing a risk validation rule."""

    def validate(self, order: OrderRequest, context: Dict[str, float]) -> None:
        """Raise :class:`ValueError` when the order violates the rule."""


@dataclass
class MaxNotionalRule:
    symbol_limits: Dict[str, float]

    def validate(self, order: OrderRequest, context: Dict[str, float]) -> None:
        price_reference = order.price or context.get("last_price", 0.0)
        notional = order.quantity * price_reference
        limit = self.symbol_limits.get(order.symbol)
        if limit is not None and notional > limit:
            raise ValueError(f"Notional {notional} exceeds limit {limit} for {order.symbol}")


@dataclass
class MaxDailyLossRule:
    max_loss: float

    def validate(self, order: OrderRequest, context: Dict[str, float]) -> None:
        estimated = order.estimated_loss or 0.0
        projected = context.get("daily_loss", 0.0) + estimated
        if projected < -abs(self.max_loss):
            raise ValueError("Daily loss limit breached")


class RiskEngine:
    """Container executing a collection of risk rules."""

    def __init__(self, rules: Iterable[RiskRule]) -> None:
        self._rules: List[RiskRule] = list(rules)

    def validate(self, order: OrderRequest, context: Dict[str, float]) -> None:
        for rule in self._rules:
            rule.validate(order, context)


__all__ = ["MaxNotionalRule", "MaxDailyLossRule", "RiskEngine", "RiskRule"]
