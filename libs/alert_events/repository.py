"""Persistence helpers for alert history records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from .models import AlertEvent


@dataclass(slots=True)
class AlertHistoryPage:
    """Container returned when paginating alert events."""

    items: Sequence[AlertEvent]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        if self.page_size <= 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size


class AlertEventRepository:
    """Repository exposing CRUD operations for alert events."""

    def __init__(self, *, default_page_size: int = 20, max_page_size: int = 100) -> None:
        self._default_page_size = default_page_size
        self._max_page_size = max_page_size

    def record_event(
        self,
        session: Session,
        *,
        trigger_id: int,
        rule_id: int,
        rule_name: str,
        strategy: str,
        severity: str,
        symbol: str,
        triggered_at: datetime,
        context: dict | None,
        source: str = "alert-engine",
        delivery_status: str = "pending",
        notification_id: int | None = None,
        notification_channel: str | None = None,
        notification_target: str | None = None,
    ) -> AlertEvent:
        """Persist an alert event and return the SQLAlchemy instance."""

        event = AlertEvent(
            trigger_id=trigger_id,
            rule_id=rule_id,
            rule_name=rule_name,
            strategy=strategy,
            severity=severity,
            symbol=symbol,
            triggered_at=triggered_at,
            context=context,
            source=source,
            delivery_status=delivery_status,
            notification_id=notification_id,
            notification_channel=notification_channel,
            notification_target=notification_target,
        )
        session.add(event)
        session.commit()
        session.refresh(event)
        return event

    def update_delivery(
        self,
        session: Session,
        event: AlertEvent,
        *,
        status: str,
        detail: str | None = None,
    ) -> AlertEvent:
        """Persist delivery information updates on an existing event."""

        event.mark_delivered(status, detail)
        session.add(event)
        session.commit()
        session.refresh(event)
        return event

    def get_by_id(self, session: Session, event_id: int) -> AlertEvent | None:
        """Return a single event by its identifier when present."""

        return session.get(AlertEvent, event_id)

    def _apply_filters(
        self,
        stmt: Select[tuple[AlertEvent]],
        *,
        start: datetime | None,
        end: datetime | None,
        strategy: str | None,
        severity: str | None,
    ) -> Select[tuple[AlertEvent]]:
        if start is not None:
            stmt = stmt.where(AlertEvent.triggered_at >= start)
        if end is not None:
            stmt = stmt.where(AlertEvent.triggered_at <= end)
        if strategy:
            stmt = stmt.where(AlertEvent.strategy == strategy)
        if severity:
            stmt = stmt.where(AlertEvent.severity == severity)
        return stmt

    def list_events(
        self,
        session: Session,
        *,
        page: int = 1,
        page_size: int | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        strategy: str | None = None,
        severity: str | None = None,
    ) -> AlertHistoryPage:
        """Return a paginated list of alert events matching optional filters."""

        if page < 1:
            page = 1
        if page_size is None:
            page_size = self._default_page_size
        page_size = max(1, min(page_size, self._max_page_size))

        stmt = select(AlertEvent).order_by(AlertEvent.triggered_at.desc())
        stmt = self._apply_filters(
            stmt,
            start=start,
            end=end,
            strategy=strategy,
            severity=severity,
        )

        total_stmt = select(func.count()).select_from(stmt.subquery())
        total = session.execute(total_stmt).scalar_one()

        offset = (page - 1) * page_size
        items = (
            session.execute(stmt.limit(page_size).offset(offset)).scalars().all()
        )
        return AlertHistoryPage(items=items, total=total, page=page, page_size=page_size)

    def list_strategies(self, session: Session) -> list[str]:
        """Return the distinct set of strategies stored in the history."""

        stmt = select(AlertEvent.strategy).distinct().order_by(AlertEvent.strategy)
        return [row[0] for row in session.execute(stmt).all() if row[0]]

    def list_severities(self, session: Session) -> list[str]:
        """Return the distinct severities stored in the history."""

        stmt = select(AlertEvent.severity).distinct().order_by(AlertEvent.severity)
        return [row[0] for row in session.execute(stmt).all() if row[0]]


__all__ = ["AlertEventRepository", "AlertHistoryPage"]
