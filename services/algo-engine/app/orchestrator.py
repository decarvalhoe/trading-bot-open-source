"""Service level state orchestration helpers."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict


@dataclass
class OrchestratorState:
    mode: str = "paper"
    daily_trade_limit: int = 100
    trades_submitted: int = 0

    def as_dict(self) -> Dict[str, int | str]:
        return {
            "mode": self.mode,
            "daily_trade_limit": self.daily_trade_limit,
            "trades_submitted": self.trades_submitted,
        }


class Orchestrator:
    """Mutable orchestrator shared by API endpoints."""

    def __init__(self) -> None:
        self._state = OrchestratorState()
        self._lock = threading.RLock()

    def get_state(self) -> OrchestratorState:
        with self._lock:
            return OrchestratorState(**self._state.__dict__)

    def set_mode(self, mode: str) -> OrchestratorState:
        if mode not in {"paper", "live"}:
            raise ValueError("mode must be either 'paper' or 'live'")
        with self._lock:
            self._state.mode = mode
            return self.get_state()

    def update_daily_limit(self, *, limit: int | None = None, trades_submitted: int | None = None) -> OrchestratorState:
        with self._lock:
            if limit is not None:
                if limit <= 0:
                    raise ValueError("daily limit must be positive")
                self._state.daily_trade_limit = limit
            if trades_submitted is not None:
                if trades_submitted < 0:
                    raise ValueError("trades submitted must be non-negative")
                self._state.trades_submitted = trades_submitted
            return self.get_state()

    def can_submit_trade(self, *, quantity: int = 1) -> bool:
        with self._lock:
            return self._state.trades_submitted + quantity <= self._state.daily_trade_limit

    def register_submission(self, *, quantity: int = 1) -> OrchestratorState:
        with self._lock:
            if not self.can_submit_trade(quantity=quantity):
                raise RuntimeError("daily trade limit exceeded")
            self._state.trades_submitted += quantity
            return self.get_state()


__all__ = ["Orchestrator", "OrchestratorState"]
