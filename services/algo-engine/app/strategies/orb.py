"""Opening range breakout strategy implementation."""
from __future__ import annotations

from typing import Any, Dict, List

from .base import StrategyBase, StrategyConfig, register_strategy


@register_strategy
class ORBStrategy(StrategyBase):
    """Naive opening range breakout implementation."""

    key = "orb"

    def generate_signals(self, market_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        opening_range = self.config.parameters.get("opening_range_minutes", 15)
        breakout_pct = self.config.parameters.get("breakout_pct", 0.2)
        candles: List[Dict[str, Any]] = market_state.get("candles", [])
        if len(candles) < opening_range:
            return []

        opening_high = max(candle["high"] for candle in candles[:opening_range])
        opening_low = min(candle["low"] for candle in candles[:opening_range])
        last_price = candles[-1]["close"]

        signals: List[Dict[str, Any]] = []
        if last_price >= opening_high * (1 + breakout_pct / 100):
            signals.append({"action": "buy", "confidence": 0.8})
        elif last_price <= opening_low * (1 - breakout_pct / 100):
            signals.append({"action": "sell", "confidence": 0.8})
        return signals


__all__ = ["ORBStrategy"]
