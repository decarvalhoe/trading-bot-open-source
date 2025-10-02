"""Helpers used to scale leader executions to follower allocations."""

from __future__ import annotations

from typing import Dict, Tuple

from schemas.market import ExecutionReport


def _coerce_positive(value: object) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    return numeric


def leader_reference_price(report: ExecutionReport) -> float:
    if report.avg_price:
        return report.avg_price
    for fill in reversed(report.fills):
        if fill.price > 0:
            return fill.price
    return 0.0


def compute_scaled_quantity(
    report: ExecutionReport,
    *,
    leverage: float,
    allocated_capital: float | None,
    risk_limits: Dict[str, object],
) -> Tuple[float, float, float]:
    """Return (quantity, price, notional) for the follower order."""

    price = leader_reference_price(report)
    if price <= 0 or report.filled_quantity <= 0:
        return 0.0, price, 0.0

    base_notional = report.filled_quantity * price
    target_notional = base_notional * max(leverage, 0.0)

    if allocated_capital is not None and allocated_capital >= 0:
        target_notional = min(target_notional, allocated_capital)

    max_notional = _coerce_positive(risk_limits.get("max_notional"))
    if max_notional is not None:
        target_notional = min(target_notional, max_notional)

    if target_notional <= 0:
        return 0.0, price, 0.0

    quantity = target_notional / price

    max_position = _coerce_positive(risk_limits.get("max_position"))
    if max_position is not None and quantity > max_position:
        quantity = max_position
        target_notional = quantity * price

    return quantity, price, target_notional


__all__ = ["compute_scaled_quantity", "leader_reference_price"]
