from __future__ import annotations

import asyncio
from collections.abc import Sequence
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from .cache import AlertContextCache
from .clients import NotificationPublisher
from .evaluator import RuleEvaluator
from .models import AlertRule, AlertTrigger
from .repository import AlertRuleRepository
from .schemas import MarketEvent


class AlertEngine:
    """Coordinates rule evaluation against incoming events and periodic checks."""

    def __init__(
        self,
        repository: AlertRuleRepository,
        evaluator: RuleEvaluator,
        context_cache: AlertContextCache,
        publisher: NotificationPublisher,
        evaluation_interval: float,
    ) -> None:
        self._repository = repository
        self._evaluator = evaluator
        self._context_cache = context_cache
        self._publisher = publisher
        self._evaluation_interval = evaluation_interval
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def handle_event(self, session: Session, event: MarketEvent) -> list[AlertTrigger]:
        rules = await self._repository.list_active_rules(session, symbol=event.symbol)
        if not rules:
            return []
        context = await self._build_context(event)
        triggers: list[AlertTrigger] = []
        for rule in rules:
            if await self._evaluate_rule(session, rule, context):
                trigger = await self._repository.record_trigger(session, rule, context)
                await self._publisher.publish(self._serialize_trigger(trigger))
                triggers.append(trigger)
        return triggers

    async def start_periodic_evaluation(self, session_factory: sessionmaker[Session]) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_periodic(session_factory))

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None

    async def _run_periodic(self, session_factory: sessionmaker[Session]) -> None:
        while True:
            if self._stop_event.is_set():
                break
            async with self._session_context(session_factory) as session:
                rules = await self._repository.list_active_rules(session)
                if rules:
                    await self._evaluate_rules_batch(session, rules)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._evaluation_interval)
            except asyncio.TimeoutError:
                continue

    async def _evaluate_rules_batch(
        self, session: Session, rules: Sequence[AlertRule]
    ) -> list[AlertTrigger]:
        triggers: list[AlertTrigger] = []
        for rule in rules:
            context = await self._build_context_from_symbol(rule.symbol)
            if await self._evaluate_rule(session, rule, context):
                trigger = await self._repository.record_trigger(session, rule, context)
                await self._publisher.publish(self._serialize_trigger(trigger))
                triggers.append(trigger)
        return triggers

    async def _evaluate_rule(self, session: Session, rule: AlertRule, context: dict[str, Any]) -> bool:
        try:
            return self._evaluator.evaluate(rule.expression, context)
        except Exception:
            return False

    async def _build_context(self, event: MarketEvent) -> dict[str, Any]:
        return await self._context_cache.build_context_for_event(event)

    async def _build_context_from_symbol(self, symbol: str) -> dict[str, Any]:
        context = await self._context_cache.build_context_for_symbol(symbol)
        context.setdefault("symbol", symbol)
        return context

    def _serialize_trigger(self, trigger: AlertTrigger) -> dict[str, Any]:
        return {
            "trigger_id": trigger.id,
            "rule_id": trigger.rule_id,
            "triggered_at": trigger.triggered_at.isoformat(),
            "context": trigger.context or {},
        }

    @asynccontextmanager
    async def _session_context(self, session_factory: sessionmaker[Session]):
        session = session_factory()
        try:
            yield session
        finally:
            session.close()
