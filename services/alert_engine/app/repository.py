from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .models import AlertRule, AlertTrigger


class AlertRuleRepository:
    """Repository handling persistence for alert rules and triggers."""

    async def list_active_rules(
        self, session: Session, symbol: str | None = None
    ) -> Sequence[AlertRule]:
        def _query() -> Sequence[AlertRule]:
            stmt = select(AlertRule).where(AlertRule.is_active.is_(True))
            if symbol is not None:
                stmt = stmt.where(AlertRule.symbol == symbol)
            return session.execute(stmt).scalars().all()

        return await asyncio.to_thread(_query)

    async def list_rules(self, session: Session) -> Sequence[AlertRule]:
        def _query() -> Sequence[AlertRule]:
            stmt = select(AlertRule).order_by(AlertRule.created_at.desc())
            return session.execute(stmt).scalars().all()

        return await asyncio.to_thread(_query)

    async def get_rule(self, session: Session, rule_id: int) -> AlertRule | None:
        def _get() -> AlertRule | None:
            return session.get(AlertRule, rule_id)

        return await asyncio.to_thread(_get)

    async def record_trigger(
        self, session: Session, rule: AlertRule, context: dict | None
    ) -> AlertTrigger:
        def _create() -> AlertTrigger:
            trigger = AlertTrigger(rule=rule, context=context)
            session.add(trigger)
            session.commit()
            session.refresh(trigger)
            return trigger

        return await asyncio.to_thread(_create)

    async def add_rule(self, session: Session, rule: AlertRule) -> AlertRule:
        def _add() -> AlertRule:
            session.add(rule)
            session.commit()
            session.refresh(rule)
            return rule

        return await asyncio.to_thread(_add)

    async def update_rule(
        self, session: Session, rule: AlertRule, values: Mapping[str, object]
    ) -> AlertRule:
        def _update() -> AlertRule:
            for field, value in values.items():
                setattr(rule, field, value)
            session.add(rule)
            session.commit()
            session.refresh(rule)
            return rule

        return await asyncio.to_thread(_update)

    async def delete_rule(self, session: Session, rule: AlertRule) -> None:
        def _delete() -> None:
            session.delete(rule)
            session.commit()

        await asyncio.to_thread(_delete)

    async def is_within_throttle(self, session: Session, rule: AlertRule) -> bool:
        def _check() -> bool:
            if not rule.throttle_seconds:
                return False
            stmt = (
                select(AlertTrigger.triggered_at)
                .where(AlertTrigger.rule_id == rule.id)
                .order_by(AlertTrigger.triggered_at.desc())
                .limit(1)
            )
            last_triggered = session.execute(stmt).scalar_one_or_none()
            if last_triggered is None:
                return False
            cutoff = datetime.utcnow() - timedelta(seconds=int(rule.throttle_seconds or 0))
            return last_triggered > cutoff

        return await asyncio.to_thread(_check)

    async def list_recent_triggers(
        self,
        session: Session,
        *,
        limit: int = 20,
    ) -> Sequence[AlertTrigger]:
        def _query() -> Sequence[AlertTrigger]:
            stmt = (
                select(AlertTrigger)
                .options(joinedload(AlertTrigger.rule))
                .order_by(AlertTrigger.triggered_at.desc())
                .limit(limit)
            )
            return session.execute(stmt).scalars().all()

        return await asyncio.to_thread(_query)
