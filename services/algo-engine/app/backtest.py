"""Simple backtesting utilities for the algo engine."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence

from .strategies.base import StrategyBase


def _safe_filename(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in name)


def _max_drawdown(equity_curve: Sequence[float]) -> float:
    peak = equity_curve[0] if equity_curve else 0.0
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        drawdown = (peak - value) / peak if peak else 0.0
        max_dd = max(max_dd, drawdown)
    return max_dd


@dataclass
class BacktestSummary:
    strategy_name: str
    trades: int
    total_return: float
    max_drawdown: float
    equity_curve: List[float] = field(default_factory=list)
    metrics_path: str = ""
    log_path: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "trades": self.trades,
            "total_return": self.total_return,
            "max_drawdown": self.max_drawdown,
            "equity_curve": self.equity_curve,
            "metrics_path": self.metrics_path,
            "log_path": self.log_path,
        }


class Backtester:
    """Runs basic long-only simulations for declarative rules."""

    def __init__(self, output_dir: Path | str = Path("data/backtests")) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        strategy: StrategyBase,
        market_data: Sequence[Dict[str, Any]],
        *,
        initial_balance: float = 10_000.0,
    ) -> BacktestSummary:
        balance = initial_balance
        position_size = 0.0
        entry_price = 0.0
        trades = 0
        logs: List[str] = []
        equity_curve: List[float] = [balance]

        for index, snapshot in enumerate(market_data):
            price = float(snapshot.get("close") or snapshot.get("price") or 0.0)
            signals = strategy.generate_signals(snapshot)
            for signal in signals:
                action = signal.get("action")
                size = float(signal.get("size", 1.0))
                if action == "buy" and position_size == 0:
                    position_size = size
                    entry_price = price
                    logs.append(f"[{index}] BUY size={size} price={price}")
                elif action == "sell" and position_size > 0:
                    pnl = (price - entry_price) * position_size
                    balance += pnl
                    trades += 1
                    logs.append(f"[{index}] SELL size={position_size} price={price} pnl={pnl}")
                    position_size = 0
                    entry_price = 0
            equity = balance
            if position_size > 0:
                equity += (price - entry_price) * position_size
            equity_curve.append(equity)

        if position_size > 0:
            final_price = float(market_data[-1].get("close") or market_data[-1].get("price") or 0.0)
            pnl = (final_price - entry_price) * position_size
            balance += pnl
            trades += 1
            logs.append(f"[final] SELL size={position_size} price={final_price} pnl={pnl}")
            equity_curve.append(balance)

        total_return = (balance - initial_balance) / initial_balance if initial_balance else 0.0
        drawdown = _max_drawdown(equity_curve)

        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        safe_name = _safe_filename(strategy.config.name)
        metrics_path = self.output_dir / f"{safe_name}_{timestamp}.json"
        log_path = self.output_dir / f"{safe_name}_{timestamp}.log"

        metrics = {
            "strategy": strategy.config.name,
            "trades": trades,
            "total_return": total_return,
            "max_drawdown": drawdown,
            "equity_curve": equity_curve,
        }
        metrics_path.write_text(json.dumps(metrics, indent=2))
        log_path.write_text("\n".join(logs))

        return BacktestSummary(
            strategy_name=strategy.config.name,
            trades=trades,
            total_return=total_return,
            max_drawdown=drawdown,
            equity_curve=equity_curve,
            metrics_path=str(metrics_path),
            log_path=str(log_path),
        )


__all__ = ["Backtester", "BacktestSummary"]
