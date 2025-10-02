"""Asynchronous worker replicating leader executions for followers."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Iterable, List, Protocol, Sequence

from schemas.market import ExecutionReport, OrderType
from schemas.order_router import ExecutionIntent

from .events import LeaderExecutionEvent
from .messaging import LeaderExecutionConsumer
from .repository import CopySubscription, CopySubscriptionRepository
from .sizing import compute_scaled_quantity, leader_reference_price

LOGGER = logging.getLogger("copy_trading.worker")


class OrderExecutionClient(Protocol):
    """Protocol describing the order router dependency used by the worker."""

    async def submit_order(self, intent: ExecutionIntent) -> ExecutionReport:
        raise NotImplementedError


class CopyTradingWorker:
    """Consume leader executions and replicate them for follower accounts."""

    def __init__(
        self,
        *,
        consumer: LeaderExecutionConsumer,
        order_executor: OrderExecutionClient,
        repository: CopySubscriptionRepository,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._consumer = consumer
        self._order_executor = order_executor
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._stopped = asyncio.Event()

    async def stop(self) -> None:
        """Request the worker loop to stop."""

        self._stopped.set()
        close = getattr(self._consumer, "close", None)
        if callable(close):
            result = close()
            if asyncio.iscoroutine(result):
                await result

    async def run_forever(self) -> None:
        """Continuously consume leader executions and replicate them."""

        while not self._stopped.is_set():
            event = await self._consumer.get()
            if event is None:
                if self._stopped.is_set():
                    break
                continue
            if self._is_copy_event(event.report.tags):
                continue
            await self._handle_event(event)

    async def _handle_event(self, event: LeaderExecutionEvent) -> None:
        subscriptions = self._repository.list_active_for_leader(
            event.leader_id, strategy=event.strategy
        )
        if not subscriptions:
            LOGGER.debug("No active followers for leader %s", event.leader_id)
            return

        leader_price = leader_reference_price(event.report)
        leader_notional = event.leader_notional()
        executed_at = self._clock()

        for subscription in subscriptions:
            if self._should_suspend(subscription):
                LOGGER.info(
                    "Subscription %s paused by risk limits", subscription.id
                )
                continue

            quantity, _, _ = compute_scaled_quantity(
                event.report,
                leverage=subscription.leverage,
                allocated_capital=subscription.allocated_capital,
                risk_limits=subscription.risk_limits,
            )
            if quantity <= 0:
                LOGGER.debug(
                    "Skipping follower %s due to zero target quantity", subscription.follower_id
                )
                continue

            intent = ExecutionIntent(
                broker=event.report.broker,
                venue=event.report.venue,
                symbol=event.report.symbol,
                side=event.report.side,
                quantity=quantity,
                order_type=OrderType.MARKET,
                account_id=subscription.follower_id,
                tags=self._build_tags(event.report.tags, subscription),
            )

            try:
                follower_report = await self._order_executor.submit_order(intent)
            except Exception as exc:  # pragma: no cover - defensive logging
                LOGGER.warning(
                    "Failed to replicate order for follower %s: %s",
                    subscription.follower_id,
                    exc,
                )
                self._repository.record_failure(
                    subscription.id, executed_at=self._clock()
                )
                continue

            divergence = self._compute_divergence(leader_price, follower_report)
            follower_price = follower_report.avg_price or leader_reference_price(
                follower_report
            )
            follower_notional = (
                follower_price * follower_report.filled_quantity
                if follower_price and follower_report.filled_quantity > 0
                else 0.0
            )
            fees = self._estimate_fees(
                leader_notional=leader_notional,
                follower_notional=follower_notional,
                leader_fees=event.fees,
            )
            status = follower_report.status.value
            self._repository.record_success(
                subscription.id,
                divergence_bps=divergence,
                fees=fees,
                status=status,
                executed_at=executed_at,
            )

    @staticmethod
    def _is_copy_event(tags: Iterable[str]) -> bool:
        for tag in tags or []:
            if isinstance(tag, str) and tag.lower() == "copy:follower":
                return True
        return False

    @staticmethod
    def _should_suspend(subscription: CopySubscription) -> bool:
        suspend = subscription.risk_limits.get("suspend")
        return bool(suspend)

    @staticmethod
    def _build_tags(base_tags: Sequence[str], subscription: CopySubscription) -> List[str]:
        tags = [tag for tag in base_tags or [] if isinstance(tag, str)]
        tags.append("copy:follower")
        tags.append(f"copy:subscription:{subscription.id}")
        tags.append(f"copy:leader:{subscription.leader_id}")
        return tags

    @staticmethod
    def _compute_divergence(
        leader_price: float, follower_report: ExecutionReport
    ) -> float | None:
        follower_price = follower_report.avg_price or leader_reference_price(
            follower_report
        )
        if leader_price <= 0 or follower_price <= 0:
            return None
        return ((follower_price - leader_price) / leader_price) * 10_000

    @staticmethod
    def _estimate_fees(
        *,
        leader_notional: float,
        follower_notional: float,
        leader_fees: float | None,
    ) -> float:
        if not leader_fees or leader_notional <= 0 or follower_notional <= 0:
            return 0.0
        scale = follower_notional / leader_notional
        return max(0.0, leader_fees * scale)


__all__ = ["CopyTradingWorker", "OrderExecutionClient"]
