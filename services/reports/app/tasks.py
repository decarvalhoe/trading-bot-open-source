from __future__ import annotations

from datetime import datetime
from typing import Iterable

try:
    from celery import Celery
except ModuleNotFoundError:  # pragma: no cover - fallback when Celery is unavailable
    class Celery:
        def __init__(self, name: str) -> None:
            self.name = name
            self.conf = type("Config", (), {"broker_url": None, "result_backend": None, "beat_schedule": {}, "timezone": "UTC"})()

        def task(self, name: str | None = None, **_: object):
            def decorator(func):
                return func

            return decorator

from sqlalchemy import select

from .calculations import ReportCalculator
from .config import get_settings
from .database import session_scope
from .tables import ReportDaily, ReportIntraday

settings = get_settings()

celery_app = Celery("reports")
celery_app.conf.broker_url = settings.celery_broker_url
celery_app.conf.result_backend = settings.celery_backend_url
celery_app.conf.beat_schedule = {
    "refresh-reports": {
        "task": "services.reports.app.tasks.refresh_reports",
        "schedule": settings.refresh_interval_seconds,
    }
}
celery_app.conf.timezone = "UTC"


def _symbols(session) -> Iterable[str]:
    daily_symbols = set(session.scalars(select(ReportDaily.symbol).distinct()))
    intraday_symbols = set(session.scalars(select(ReportIntraday.symbol).distinct()))
    return sorted(daily_symbols | intraday_symbols)


@celery_app.task(name="services.reports.app.tasks.refresh_reports")
def refresh_reports() -> dict[str, datetime]:
    refreshed: dict[str, datetime] = {}
    with session_scope() as session:
        for symbol in _symbols(session):
            calculator = ReportCalculator(session)
            report = calculator.persist_snapshot(symbol)
            timestamp = max(
                filter(
                    None,
                    [
                        report.daily.updated_at if report.daily else None,
                        report.intraday.updated_at if report.intraday else None,
                    ],
                ),
                default=datetime.utcnow(),
            )
            refreshed[symbol] = timestamp
    return refreshed


__all__ = ["celery_app", "refresh_reports"]
