"""Gap fill strategy implementation."""
from __future__ import annotations

from typing import Any, Dict, List

from .base import StrategyBase, StrategyConfig, register_strategy


@register_strategy
class GapFillStrategy(StrategyBase):
    """Look for overnight gaps and fade them when momentum wanes."""

    key = "gap_fill"

    def generate_signals(self, market_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        gap_threshold = self.config.parameters.get("gap_pct", 1.0)
        fade_pct = self.config.parameters.get("fade_pct", 0.5)
        prev_close = market_state.get("previous_close")
        open_price = market_state.get("open")
        last_price = market_state.get("last")
        if prev_close is None or open_price is None or last_price is None:
            return []

        gap = ((open_price - prev_close) / prev_close) * 100
        signals: List[Dict[str, Any]] = []
        if abs(gap) >= gap_threshold and abs(((last_price - open_price) / open_price) * 100) <= fade_pct:
            direction = "sell" if gap > 0 else "buy"
            signals.append({"action": direction, "confidence": 0.6})
        return signals


__all__ = ["GapFillStrategy"]
