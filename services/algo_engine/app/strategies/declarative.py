"""Declarative strategy implementation evaluated against market state."""

from __future__ import annotations

import operator
from typing import Any, Dict, Mapping

from .base import StrategyBase, register_strategy

OPERATORS: Mapping[str, Any] = {
    "eq": operator.eq,
    "ne": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
}


def _resolve(path: str, state: Mapping[str, Any]) -> Any:
    current: Any = state
    for part in path.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        else:
            return None
    return current


def _evaluate_condition(condition: Mapping[str, Any], state: Mapping[str, Any]) -> bool:
    if "all" in condition:
        return all(_evaluate_condition(sub, state) for sub in condition["all"])
    if "any" in condition:
        return any(_evaluate_condition(sub, state) for sub in condition["any"])

    field = condition.get("field")
    operator_key = condition.get("operator", "eq")
    target = condition.get("value")

    if not isinstance(field, str):
        return False
    op = OPERATORS.get(str(operator_key).lower())
    if op is None:
        raise ValueError(f"Unsupported operator '{operator_key}' in declarative rule")
    actual = _resolve(field, state)
    return op(actual, target)


@register_strategy
class DeclarativeStrategy(StrategyBase):
    key = "declarative"

    def __init__(self, config):  # type: ignore[override]
        super().__init__(config)
        definition = config.parameters.get("definition", {})
        if not isinstance(definition, Mapping):
            raise ValueError("Declarative strategies require a 'definition' mapping in parameters")
        self._rules = list(definition.get("rules", []))
        if not isinstance(self._rules, list):
            raise ValueError("Declarative strategy rules must be a list")

    def generate_signals(self, market_state: Dict[str, Any]) -> list[Dict[str, Any]]:  # type: ignore[override]
        signals: list[Dict[str, Any]] = []
        for rule in self._rules:
            when = rule.get("when", {})
            signal = rule.get("signal", {})
            if not when or not signal:
                continue
            if _evaluate_condition(when, market_state):
                signals.append(dict(signal))
        return signals


__all__ = ["DeclarativeStrategy"]
