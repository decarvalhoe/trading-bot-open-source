"""Sandbox Binance adapter returning deterministic execution reports."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from providers.binance import BinanceClient, BinanceError, normalize_symbol as normalize_binance_symbol
from schemas.market import ExecutionFill, ExecutionStatus, OrderRequest
from schemas.order_router import ExecutionReport

from .base import BrokerAdapter


def _map_status(value: str | None) -> ExecutionStatus:
    if not value:
        return ExecutionStatus.ACCEPTED
    upper = value.upper()
    if "PART" in upper:
        return ExecutionStatus.PARTIALLY_FILLED
    if upper in {"FILLED", "FILLS"}:
        return ExecutionStatus.FILLED
    if upper in {"CANCELED", "CANCELLED"}:
        return ExecutionStatus.CANCELLED
    if upper in {"REJECTED", "REJECT"}:
        return ExecutionStatus.REJECTED
    return ExecutionStatus.ACCEPTED


class BinanceAdapter(BrokerAdapter):
    name = "binance"

    def __init__(self, client: BinanceClient | None = None) -> None:
        super().__init__()
        self._client = client

    def place_order(self, order: OrderRequest, *, reference_price: float) -> ExecutionReport:
        symbol = normalize_binance_symbol(order.symbol)
        if self._client is None:
            price = reference_price if reference_price > 0 else 1.0
            order_id = f"BN-{len(self.reports()) + 1}"
            timestamp = datetime.now(timezone.utc)
            fill = ExecutionFill(
                quantity=order.quantity,
                price=price,
                timestamp=timestamp,
            )
            report = ExecutionReport(
                order_id=order_id,
                status=ExecutionStatus.FILLED,
                broker=self.name,
                venue=order.venue,
                symbol=symbol,
                side=order.side,
                quantity=order.quantity,
                filled_quantity=order.quantity,
                avg_price=price,
                submitted_at=timestamp,
                fills=[fill],
                tags=order.tags,
            )
            return self._store_report(report)

        try:
            payload = self._client.place_order(
                symbol=symbol,
                side=order.side.value,
                order_type=order.order_type.value,
                quantity=order.quantity,
                price=order.price,
                time_in_force=order.time_in_force.value,
            )
        except BinanceError as exc:  # pragma: no cover - defensive safety net
            raise RuntimeError(f"Binance order failed: {exc}") from exc

        filled_quantity = float(payload.get("executedQty") or 0.0)
        fills_payload: Iterable[dict[str, object]] = payload.get("fills") or []
        fills: list[ExecutionFill] = []
        total_notional = 0.0
        if fills_payload:
            for raw_fill in fills_payload:
                qty = float(raw_fill.get("qty") or raw_fill.get("quantity") or 0.0)
                price = float(raw_fill.get("price") or 0.0)
                if qty <= 0 or price <= 0:
                    continue
                timestamp = datetime.now(timezone.utc)
                fills.append(
                    ExecutionFill(
                        quantity=qty,
                        price=price,
                        timestamp=timestamp,
                    )
                )
                filled_quantity += qty
                total_notional += qty * price
        avg_price = None
        if filled_quantity > 0:
            avg_price = total_notional / filled_quantity if total_notional > 0 else None
        if avg_price is None:
            price = float(payload.get("price") or payload.get("avgPrice") or 0.0)
            if price <= 0:
                price = reference_price if reference_price > 0 else 1.0
            avg_price = price
        submitted_ms = payload.get("transactTime")
        if isinstance(submitted_ms, (int, float)):
            submitted_at = datetime.fromtimestamp(submitted_ms / 1_000, tz=timezone.utc)
        else:
            submitted_at = datetime.now(timezone.utc)
        order_id = str(payload.get("orderId") or f"BN-{len(self.reports()) + 1}")
        report = ExecutionReport(
            order_id=order_id,
            status=_map_status(payload.get("status") if isinstance(payload, dict) else None),
            broker=self.name,
            venue=order.venue,
            symbol=symbol,
            side=order.side,
            quantity=order.quantity,
            filled_quantity=filled_quantity,
            avg_price=avg_price,
            submitted_at=submitted_at,
            fills=fills,
            tags=order.tags,
        )
        return self._store_report(report)


__all__ = ["BinanceAdapter"]
