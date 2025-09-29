from __future__ import annotations

import asyncio
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AlertRule, AlertTrigger


class AlertRuleRepository:
    """Repository handling persistence for alert rules and triggers."""

    async def list_active_rules(self, session: Session, symbol: str | None = None) -> Sequence[AlertRule]:
        def _query() -> Sequence[AlertRule]:
            stmt = select(AlertRule).where(AlertRule.is_active.is_(True))
            if symbol is not None:
                stmt = stmt.where(AlertRule.symbol == symbol)
            return session.execute(stmt).scalars().all()

        return await asyncio.to_thread(_query)

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
