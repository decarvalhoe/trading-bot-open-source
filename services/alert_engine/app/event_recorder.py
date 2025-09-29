"""Bridge between alert engine triggers and the shared alert event store."""

from __future__ import annotations

import asyncio
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Callable, Protocol

from sqlalchemy.orm import Session

from libs.alert_events import AlertEventRepository
from libs.db.db import SessionLocal

from .models import AlertTrigger


class SessionFactory(Protocol):
    def __call__(self) -> AbstractContextManager[Session]:  # pragma: no cover - typing hook
        ...


@dataclass(slots=True)
class AlertEventRecorder:
    """Persist triggers in the shared alert history store."""

    repository: AlertEventRepository
    session_factory: Callable[[], Session]

    def __post_init__(self) -> None:
        session = self.session_factory()
        try:
            engine = session.get_bind()
            if engine is not None:
                from libs.alert_events import AlertEventBase

                AlertEventBase.metadata.create_all(bind=engine)
        finally:
            session.close()

    @classmethod
    def from_defaults(cls) -> "AlertEventRecorder":
        return cls(repository=AlertEventRepository(), session_factory=SessionLocal)

    async def record(
        self, trigger: AlertTrigger, *, source: str = "alert-engine"
    ) -> "AlertEvent":
        """Persist a trigger asynchronously to avoid blocking the event loop."""

        def _persist():
            session = self.session_factory()
            try:
                rule = trigger.rule
                strategy = (rule.name if rule else "unknown").strip() or "unknown"
                severity = rule.severity if rule else "info"
                symbol = rule.symbol if rule else "UNKNOWN"
                return self.repository.record_event(
                    session,
                    trigger_id=trigger.id,
                    rule_id=trigger.rule_id,
                    rule_name=rule.name if rule else "unknown",
                    strategy=strategy,
                    severity=severity,
                    symbol=symbol,
                    triggered_at=trigger.triggered_at,
                    context=trigger.context or {},
                    source=source,
                )
            finally:
                session.close()

        return await asyncio.to_thread(_persist)


__all__ = ["AlertEventRecorder"]
