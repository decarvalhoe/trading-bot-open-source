"""Domain events consumed by the copy-trading worker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from schemas.market import ExecutionReport


@dataclass(slots=True)
class LeaderExecutionEvent:
    """Execution emitted by a leader strategy that should be replicated."""

    leader_id: str
    strategy: str
    report: ExecutionReport
    fees: Optional[float] = None

    def leader_notional(self) -> float:
        """Return the executed notional for the leader order."""

        price = self.report.avg_price or self._last_fill_price()
        if not price or self.report.filled_quantity <= 0:
            return 0.0
        return price * self.report.filled_quantity

    def _last_fill_price(self) -> float:
        for fill in reversed(self.report.fills):
            if fill.price > 0:
                return fill.price
        return 0.0


__all__ = ["LeaderExecutionEvent"]
