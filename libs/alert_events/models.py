"""SQLAlchemy models describing persisted alert trigger events."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Integer, String
from sqlalchemy.orm import declarative_base

AlertEventBase = declarative_base()


class AlertEvent(AlertEventBase):
    """Historical record capturing a trigger handled by the alerting stack."""

    __tablename__ = "alert_events"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    trigger_id: int = Column(Integer, nullable=False, index=True)
    rule_id: int = Column(Integer, nullable=False, index=True)
    rule_name: str = Column(String(255), nullable=False)
    strategy: str = Column(String(128), nullable=False)
    severity: str = Column(String(32), nullable=False, index=True)
    symbol: str = Column(String(32), nullable=False, index=True)
    triggered_at: datetime = Column(DateTime, nullable=False, index=True)
    created_at: datetime = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    context: dict | None = Column(JSON, nullable=True)

    source: str = Column(String(64), nullable=False, default="alert-engine", index=True)
    delivery_status: str = Column(String(32), nullable=False, default="pending", index=True)
    delivery_detail: str | None = Column(String(255), nullable=True)

    notification_id: int | None = Column(Integer, nullable=True)
    notification_channel: str | None = Column(String(32), nullable=True, index=True)
    notification_target: str | None = Column(String(255), nullable=True)
    notification_type: str | None = Column(String(32), nullable=True, index=True)

    def mark_delivered(self, status: str, detail: str | None = None) -> None:
        """Update delivery information for the event."""

        self.delivery_status = status
        self.delivery_detail = detail


__all__ = ["AlertEvent", "AlertEventBase"]
