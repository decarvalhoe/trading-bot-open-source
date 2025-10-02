"""Database access layer for copy-trading subscriptions."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterator, List

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from infra import Listing, MarketplaceSubscription
from libs.db.db import SessionLocal


@dataclass(slots=True)
class CopySubscription:
    """Projection of a copy-trading subscription used by the worker."""

    id: int
    follower_id: str
    leader_id: str
    strategy_name: str
    leverage: float
    allocated_capital: float | None
    risk_limits: Dict[str, Any]


class CopySubscriptionRepository:
    """Repository retrieving subscriptions and recording replication outcomes."""

    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    @contextmanager
    def _session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()

    def list_active_for_leader(
        self, leader_id: str, *, strategy: str | None = None
    ) -> List[CopySubscription]:
        stmt: Select = (
            select(MarketplaceSubscription, Listing)
            .join(Listing, MarketplaceSubscription.listing_id == Listing.id)
            .where(MarketplaceSubscription.status == "active", Listing.owner_id == leader_id)
        )
        if strategy:
            stmt = stmt.where(Listing.strategy_name == strategy)

        subscriptions: List[CopySubscription] = []
        with self._session() as session:
            for subscription, listing in session.execute(stmt).all():
                subscriptions.append(
                    CopySubscription(
                        id=subscription.id,
                        follower_id=subscription.subscriber_id,
                        leader_id=listing.owner_id,
                        strategy_name=listing.strategy_name,
                        leverage=float(subscription.leverage or 1.0),
                        allocated_capital=subscription.allocated_capital,
                        risk_limits=dict(subscription.risk_limits or {}),
                    )
                )
        return subscriptions

    def record_success(
        self,
        subscription_id: int,
        *,
        divergence_bps: float | None,
        fees: float,
        status: str,
        executed_at: datetime,
    ) -> None:
        with self._session() as session:
            subscription = session.get(MarketplaceSubscription, subscription_id)
            if not subscription:
                return
            subscription.replication_status = status
            subscription.divergence_bps = divergence_bps
            raw_previous = subscription.total_fees_paid or 0.0
            try:
                previous_fees = float(raw_previous)
            except (TypeError, ValueError):
                previous_fees = 0.0
            subscription.total_fees_paid = max(0.0, previous_fees + max(fees, 0.0))
            if executed_at.tzinfo is None:
                executed_at = executed_at.replace(tzinfo=timezone.utc)
            else:
                executed_at = executed_at.astimezone(timezone.utc)
            subscription.last_synced_at = executed_at
            session.commit()

    def record_failure(
        self,
        subscription_id: int,
        *,
        executed_at: datetime | None = None,
    ) -> None:
        with self._session() as session:
            subscription = session.get(MarketplaceSubscription, subscription_id)
            if not subscription:
                return
            subscription.replication_status = "error"
            if executed_at:
                if executed_at.tzinfo is None:
                    executed_at = executed_at.replace(tzinfo=timezone.utc)
                else:
                    executed_at = executed_at.astimezone(timezone.utc)
                subscription.last_synced_at = executed_at
            session.commit()


__all__ = ["CopySubscription", "CopySubscriptionRepository"]
