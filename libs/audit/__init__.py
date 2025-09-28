"""Helpers to record audit trail events."""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from infra import AuditLog


def record_audit(
    db: Session,
    *,
    service: str,
    action: str,
    actor_id: str,
    subject_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    message: Optional[str] = None,
) -> AuditLog:
    """Persist an :class:`AuditLog` entry and return it."""

    entry = AuditLog(
        service=service,
        action=action,
        actor_id=actor_id,
        subject_id=subject_id,
        details=details or {},
        message=message,
    )
    db.add(entry)
    db.flush()
    return entry


__all__ = ["record_audit"]
