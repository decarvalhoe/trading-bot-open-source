"""Paper IBKR broker adapter used by the sandbox order router."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from providers.ibkr import IBKRClient, IBKRError, normalize_symbol as normalize_ibkr_symbol
from schemas.market import ExecutionFill, ExecutionStatus, OrderRequest
from schemas.order_router import ExecutionReport

from .base import BrokerAdapter


def _map_status(value: str | None, *, filled: float, total: float) -> ExecutionStatus:
    if not value:
        if filled <= 0:
            return ExecutionStatus.ACCEPTED
        if filled < total:
            return ExecutionStatus.PARTIALLY_FILLED
        return ExecutionStatus.FILLED
    upper = value.upper()
    if "PART" in upper:
        return ExecutionStatus.PARTIALLY_FILLED
    if upper in {"FILLED", "COMPLETED", "EXECUTED"}:
        return ExecutionStatus.FILLED
    if upper in {"CANCELED", "CANCELLED"}:
        return ExecutionStatus.CANCELLED
    if upper in {"REJECTED", "ERROR"}:
        return ExecutionStatus.REJECTED
    return ExecutionStatus.ACCEPTED


class IBKRAdapter(BrokerAdapter):
    name = "ibkr"

    def __init__(self, client: IBKRClient | None = None) -> None:
        super().__init__()
        self._client = client

    def place_order(self, order: OrderRequest, *, reference_price: float) -> ExecutionReport:
        symbol = normalize_ibkr_symbol(order.symbol)
        if self._client is None:
            order_id = f"IB-{len(self.reports()) + 1}"
            fill_price = reference_price if reference_price > 0 else 1.0
            filled_quantity = order.quantity * 0.95
            timestamp = datetime.now(timezone.utc)
            fill = ExecutionFill(
                quantity=filled_quantity,
                price=fill_price,
                timestamp=timestamp,
            )
            status = (
                ExecutionStatus.PARTIALLY_FILLED
                if filled_quantity < order.quantity
                else ExecutionStatus.FILLED
            )
            report = ExecutionReport(
                order_id=order_id,
                status=status,
                broker=self.name,
                venue=order.venue,
                symbol=symbol,
                side=order.side,
                quantity=order.quantity,
                filled_quantity=filled_quantity,
                avg_price=fill_price,
                submitted_at=timestamp,
                fills=[fill],
                tags=order.tags,
            )
            return self._store_report(report)

        account_id = getattr(order, "account_id", None)
        if not isinstance(account_id, str) or not account_id:
            account_id = None
        try:
            payload = self._client.place_order(
                symbol=symbol,
                side=order.side.value,
                quantity=order.quantity,
                order_type=order.order_type.value,
                price=order.price,
                time_in_force=order.time_in_force.value,
                account_id=account_id,
            )
        except IBKRError as exc:  # pragma: no cover - defensive safety net
            raise RuntimeError(f"IBKR order failed: {exc}") from exc

        filled_quantity = float(
            payload.get("filledQuantity")
            or payload.get("filled")
            or payload.get("executedQuantity")
            or 0.0
        )
        avg_price = payload.get("avgPrice") or payload.get("averagePrice")
        avg_price_value = float(avg_price) if avg_price is not None else 0.0
        fills_payload: Iterable[dict[str, object]] = (
            payload.get("fills") or payload.get("executions") or []
        )
        fills: list[ExecutionFill] = []
        total_notional = 0.0
        if fills_payload:
            for raw_fill in fills_payload:
                qty = float(raw_fill.get("qty") or raw_fill.get("quantity") or 0.0)
                price = float(raw_fill.get("price") or raw_fill.get("avgPrice") or 0.0)
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
                total_notional += qty * price
            if total_notional > 0 and filled_quantity <= 0:
                filled_quantity = sum(fill.quantity for fill in fills)
            if total_notional > 0 and filled_quantity > 0:
                avg_price_value = total_notional / filled_quantity
        if avg_price_value <= 0:
            avg_price_value = reference_price if reference_price > 0 else 1.0
        submitted = payload.get("timestamp") or payload.get("submittedAt")
        if isinstance(submitted, (int, float)):
            submitted_at = datetime.fromtimestamp(float(submitted), tz=timezone.utc)
        elif isinstance(submitted, str):
            try:
                submitted_at = datetime.fromisoformat(submitted)
                if submitted_at.tzinfo is None:
                    submitted_at = submitted_at.replace(tzinfo=timezone.utc)
            except ValueError:
                submitted_at = datetime.now(timezone.utc)
        else:
            submitted_at = datetime.now(timezone.utc)
        order_id = str(payload.get("orderId") or payload.get("id") or f"IB-{len(self.reports()) + 1}")
        report = ExecutionReport(
            order_id=order_id,
            status=_map_status(payload.get("status"), filled=filled_quantity, total=order.quantity),
            broker=self.name,
            venue=order.venue,
            symbol=symbol,
            side=order.side,
            quantity=order.quantity,
            filled_quantity=filled_quantity,
            avg_price=avg_price_value,
            submitted_at=submitted_at,
            fills=fills,
            tags=order.tags,
        )
        return self._store_report(report)


__all__ = ["IBKRAdapter"]
