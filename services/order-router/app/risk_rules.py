"""Risk management primitives and configurable rules for the order router."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Mapping, Protocol, runtime_checkable

from schemas.market import OrderRequest, OrderSide

RiskContext = Dict[str, float | int | str | None]


class RiskLevel(str, Enum):
    """Severity of a risk signal."""

    ALERT = "alert"
    LOCK = "lock"


@dataclass
class RiskSignal:
    """Outcome of a risk rule evaluation."""

    rule_id: str
    level: RiskLevel
    message: str
    metadata: Dict[str, float | int | str | None] = field(default_factory=dict)


@runtime_checkable
class RiskRule(Protocol):
    """Protocol describing a risk validation rule."""

    rule_id: str
    description: str

    def evaluate(self, order: OrderRequest, context: RiskContext) -> List[RiskSignal]:
        ...


@runtime_checkable
class SupportsExecutionHook(Protocol):
    """Optional protocol for rules needing execution callbacks."""

    def register_execution(self, order: OrderRequest, account_id: str, price: float) -> None:
        ...


@dataclass(frozen=True)
class SymbolLimit:
    """Position and notional constraints for a symbol."""

    max_position: float
    max_notional: float


class DynamicLimitStore:
    """Maintain positions, overrides and stop-loss configuration per account."""

    def __init__(self, baseline: Mapping[str, SymbolLimit]):
        self._baseline: Dict[str, SymbolLimit] = dict(baseline)
        self._overrides: Dict[str, Dict[str, SymbolLimit]] = {}
        self._positions: Dict[tuple[str, str], float] = {}
        self._stop_losses: Dict[str, float] = {}

    def set_account_limit(self, account: str, symbol: str, limit: SymbolLimit) -> None:
        self._overrides.setdefault(account, {})[symbol] = limit

    def get_limit(self, account: str, symbol: str) -> SymbolLimit | None:
        override = self._overrides.get(account, {}).get(symbol)
        if override:
            return override
        return self._baseline.get(symbol)

    def project_position(self, account: str, symbol: str, delta: float) -> float:
        key = (account, symbol)
        return self._positions.get(key, 0.0) + delta

    def commit(self, account: str, symbol: str, delta: float) -> None:
        key = (account, symbol)
        self._positions[key] = self._positions.get(key, 0.0) + delta

    def position(self, account: str, symbol: str) -> float:
        key = (account, symbol)
        return self._positions.get(key, 0.0)

    def set_stop_loss(self, account: str, threshold: float) -> None:
        self._stop_losses[account] = abs(threshold)

    def get_stop_loss(self, account: str) -> float | None:
        return self._stop_losses.get(account)


@dataclass
class MaxNotionalRule:
    """Backward compatibility wrapper for static notional limits."""

    symbol_limits: Dict[str, float]
    rule_id: str = "max_notional"
    description: str = "Static notional guard"

    def evaluate(self, order: OrderRequest, context: RiskContext) -> List[RiskSignal]:
        price_reference = float(order.price or context.get("last_price", 0.0) or 0.0)
        notional = order.quantity * price_reference
        limit = self.symbol_limits.get(order.symbol)
        if limit is not None and notional > limit:
            return [
                RiskSignal(
                    rule_id=self.rule_id,
                    level=RiskLevel.LOCK,
                    message=f"Notional {notional:.2f} exceeds limit {limit:.2f} for {order.symbol}",
                    metadata={"symbol": order.symbol, "notional": notional, "limit": limit},
                )
            ]
        return []


@dataclass
class DynamicLimitRule:
    """Validate account level dynamic limits on the fly."""

    store: DynamicLimitStore
    alert_ratio: float = 0.8
    rule_id: str = "dynamic_limits"
    description: str = "Dynamic per-account/per-symbol limits"

    def evaluate(self, order: OrderRequest, context: RiskContext) -> List[RiskSignal]:
        account_id = str(context.get("account_id") or "default")
        limit = self.store.get_limit(account_id, order.symbol)
        if limit is None:
            return []

        price_reference = float(order.price or context.get("last_price") or 0.0)
        if price_reference <= 0:
            price_reference = 1.0

        side_factor = 1.0 if order.side is OrderSide.BUY else -1.0
        projected_position = self.store.project_position(account_id, order.symbol, side_factor * order.quantity)
        projected_notional = abs(projected_position) * price_reference

        if abs(projected_position) > limit.max_position:
            return [
                RiskSignal(
                    rule_id=self.rule_id,
                    level=RiskLevel.LOCK,
                    message=(
                        f"Projected position {projected_position:.4f} exceeds limit "
                        f"{limit.max_position:.4f} for {account_id}:{order.symbol}"
                    ),
                    metadata={
                        "account": account_id,
                        "symbol": order.symbol,
                        "position": projected_position,
                        "max_position": limit.max_position,
                    },
                )
            ]

        signals: List[RiskSignal] = []
        if projected_notional > limit.max_notional:
            signals.append(
                RiskSignal(
                    rule_id=self.rule_id,
                    level=RiskLevel.LOCK,
                    message=(
                        f"Projected notional {projected_notional:.2f} exceeds limit "
                        f"{limit.max_notional:.2f} for {account_id}:{order.symbol}"
                    ),
                    metadata={
                        "account": account_id,
                        "symbol": order.symbol,
                        "notional": projected_notional,
                        "max_notional": limit.max_notional,
                    },
                )
            )
        elif projected_notional > limit.max_notional * self.alert_ratio:
            signals.append(
                RiskSignal(
                    rule_id=self.rule_id,
                    level=RiskLevel.ALERT,
                    message=(
                        f"Notional usage {projected_notional:.2f} near limit {limit.max_notional:.2f} "
                        f"for {account_id}:{order.symbol}"
                    ),
                    metadata={
                        "account": account_id,
                        "symbol": order.symbol,
                        "notional": projected_notional,
                        "max_notional": limit.max_notional,
                    },
                )
            )
        return signals

    def register_execution(self, order: OrderRequest, account_id: str, price: float) -> None:
        side_factor = 1.0 if order.side is OrderSide.BUY else -1.0
        self.store.commit(account_id, order.symbol, side_factor * order.quantity)


@dataclass
class MaxDailyLossRule:
    max_loss: float
    rule_id: str = "max_daily_loss"
    description: str = "Aggregate daily loss guard"

    def evaluate(self, order: OrderRequest, context: RiskContext) -> List[RiskSignal]:
        estimated = float(order.estimated_loss or 0.0)
        projected = float(context.get("daily_loss") or 0.0) + estimated
        if projected < -abs(self.max_loss):
            return [
                RiskSignal(
                    rule_id=self.rule_id,
                    level=RiskLevel.LOCK,
                    message="Daily loss limit breached",
                    metadata={"projected": projected, "limit": -abs(self.max_loss)},
                )
            ]
        return []


@dataclass
class StopLossRule:
    store: DynamicLimitStore
    default_threshold: float
    alert_ratio: float = 0.8
    rule_id: str = "stop_loss"
    description: str = "Account level stop-loss"

    def evaluate(self, order: OrderRequest, context: RiskContext) -> List[RiskSignal]:
        account_id = str(context.get("account_id") or "default")
        threshold = context.get("stop_loss")
        if threshold is None:
            threshold = self.store.get_stop_loss(account_id)
        if threshold is None:
            threshold = self.default_threshold
        threshold = abs(float(threshold))

        realized = float(context.get("realized_pnl") or 0.0)
        unrealized = float(context.get("unrealized_pnl") or 0.0)
        current = realized + unrealized

        signals: List[RiskSignal] = []
        if current <= -threshold:
            signals.append(
                RiskSignal(
                    rule_id=self.rule_id,
                    level=RiskLevel.LOCK,
                    message=(
                        f"Account {account_id} breached stop-loss threshold: {current:.2f} <= -{threshold:.2f}"
                    ),
                    metadata={
                        "account": account_id,
                        "current_pnl": current,
                        "threshold": -threshold,
                    },
                )
            )
        elif current <= -threshold * self.alert_ratio:
            signals.append(
                RiskSignal(
                    rule_id=self.rule_id,
                    level=RiskLevel.ALERT,
                    message=(
                        f"Account {account_id} approaching stop-loss: {current:.2f} <= -{threshold * self.alert_ratio:.2f}"
                    ),
                    metadata={
                        "account": account_id,
                        "current_pnl": current,
                        "threshold": -threshold,
                    },
                )
            )
        return signals


class RiskEngine:
    """Container executing a collection of risk rules."""

    def __init__(self, rules: Iterable[RiskRule]):
        self._rules: List[RiskRule] = list(rules)

    def evaluate(self, order: OrderRequest, context: RiskContext) -> List[RiskSignal]:
        signals: List[RiskSignal] = []
        for rule in self._rules:
            signals.extend(rule.evaluate(order, context))
        return signals

    def validate(self, order: OrderRequest, context: RiskContext) -> List[RiskSignal]:
        signals = self.evaluate(order, context)
        locks = [signal for signal in signals if signal.level is RiskLevel.LOCK]
        if locks:
            # Raise the first blocking signal and allow the caller to inspect any alerts.
            raise ValueError(locks[0].message)
        return [signal for signal in signals if signal.level is RiskLevel.ALERT]

    def register_execution(self, order: OrderRequest, account_id: str, price: float) -> None:
        for rule in self._rules:
            if isinstance(rule, SupportsExecutionHook):
                rule.register_execution(order, account_id, price)


__all__ = [
    "DynamicLimitRule",
    "DynamicLimitStore",
    "MaxDailyLossRule",
    "MaxNotionalRule",
    "RiskEngine",
    "RiskLevel",
    "RiskRule",
    "RiskSignal",
    "StopLossRule",
    "SymbolLimit",
]
