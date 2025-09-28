"""Sample data served by the web dashboard service."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import List

from .schemas import Alert, DashboardContext, Holding, Portfolio, RiskLevel, Transaction


def _build_portfolios() -> List[Portfolio]:
    return [
        Portfolio(
            name="Growth",
            owner="alice",
            holdings=[
                Holding(symbol="AAPL", quantity=12, average_price=154.2, current_price=178.4),
                Holding(symbol="MSFT", quantity=5, average_price=298.1, current_price=310.6),
            ],
        ),
        Portfolio(
            name="Income",
            owner="bob",
            holdings=[
                Holding(symbol="TLT", quantity=20, average_price=100.5, current_price=98.2),
                Holding(symbol="XOM", quantity=15, average_price=88.5, current_price=105.7),
            ],
        ),
    ]


def _build_transactions() -> List[Transaction]:
    base_time = datetime.utcnow()
    return [
        Transaction(
            timestamp=base_time - timedelta(hours=2),
            symbol="AAPL",
            side="buy",
            quantity=5,
            price=177.9,
            portfolio="Growth",
        ),
        Transaction(
            timestamp=base_time - timedelta(hours=5),
            symbol="XOM",
            side="sell",
            quantity=3,
            price=104.1,
            portfolio="Income",
        ),
        Transaction(
            timestamp=base_time - timedelta(days=1, hours=1),
            symbol="BTC-USD",
            side="buy",
            quantity=0.25,
            price=Decimal("43750.00"),
            portfolio="Growth",
        ),
    ]


def _build_alerts() -> List[Alert]:
    base_time = datetime.utcnow()
    return [
        Alert(
            id="maint-margin",
            title="Maintenance margin nearing threshold",
            detail="Portfolio Growth is at 82% of the allowed maintenance margin.",
            risk=RiskLevel.warning,
            created_at=base_time - timedelta(minutes=35),
        ),
        Alert(
            id="drawdown",
            title="Daily drawdown limit exceeded",
            detail="Income portfolio dropped 6% over the last trading session.",
            risk=RiskLevel.critical,
            created_at=base_time - timedelta(hours=7),
        ),
        Alert(
            id="news",
            title="Breaking news on AAPL",
            detail="Apple announces quarterly earnings call for next Tuesday.",
            risk=RiskLevel.info,
            created_at=base_time - timedelta(hours=1, minutes=10),
            acknowledged=True,
        ),
    ]


def load_dashboard_context() -> DashboardContext:
    """Return consistent sample data for the dashboard view."""

    return DashboardContext(
        portfolios=_build_portfolios(),
        transactions=_build_transactions(),
        alerts=_build_alerts(),
    )


__all__ = [
    "load_dashboard_context",
]

