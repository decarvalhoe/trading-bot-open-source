"""Reusable audit trail models shared across services."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class AuditLog(Base):
    """Represents an audit log entry tracking user actions."""

    __tablename__ = "audit_logs"

    id: int = Column(Integer, primary_key=True)
    service: str = Column(String(64), nullable=False, index=True)
    action: str = Column(String(64), nullable=False)
    actor_id: str = Column(String(64), nullable=False, index=True)
    subject_id: Optional[str] = Column(String(64), nullable=True, index=True)
    details: Dict[str, object] = Column(JSON, nullable=False, default=dict)
    message: Optional[str] = Column(Text)
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = ["Base", "AuditLog"]
