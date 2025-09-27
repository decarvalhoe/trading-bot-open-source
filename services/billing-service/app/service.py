"""Domain helpers manipulating the entitlements storage."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from infra import EntitlementsCache, Feature, Plan, PlanFeature, Subscription


def upsert_plan(db: Session, *, code: str, name: str, stripe_price_id: str, description: Optional[str] = None) -> Plan:
    plan = db.scalar(select(Plan).where(Plan.code == code))
    if plan:
        plan.name = name
        plan.stripe_price_id = stripe_price_id
        plan.description = description
    else:
        plan = Plan(code=code, name=name, stripe_price_id=stripe_price_id, description=description)
        db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def upsert_feature(db: Session, *, code: str, name: str, kind: str = "capability", description: Optional[str] = None) -> Feature:
    feature = db.scalar(select(Feature).where(Feature.code == code))
    if feature:
        feature.name = name
        feature.kind = kind
        feature.description = description
    else:
        feature = Feature(code=code, name=name, kind=kind, description=description)
        db.add(feature)
    db.commit()
    db.refresh(feature)
    return feature


def attach_features(db: Session, plan: Plan, features: Iterable[tuple[Feature, Optional[int]]]) -> None:
    existing = {pf.feature_id: pf for pf in plan.features}
    for feature, limit in features:
        pf = existing.get(feature.id)
        if pf:
            pf.limit = limit
        else:
            plan.features.append(PlanFeature(feature=feature, limit=limit))
    db.commit()


def update_subscription(
    db: Session,
    *,
    customer_id: str,
    plan: Plan,
    status: str,
    current_period_end: Optional[datetime] = None,
) -> Subscription:
    sub = db.scalar(
        select(Subscription).where(Subscription.customer_id == customer_id, Subscription.status == status)
    )
    if sub:
        sub.plan = plan
        sub.current_period_end = current_period_end
    else:
        sub = Subscription(
            customer_id=customer_id,
            plan=plan,
            status=status,
            current_period_end=current_period_end,
        )
        db.add(sub)
    db.commit()
    db.refresh(sub)
    invalidate_cache(db, customer_id)
    return sub


def deactivate_subscription(db: Session, *, customer_id: str) -> None:
    subs = db.scalars(select(Subscription).where(Subscription.customer_id == customer_id)).all()
    for sub in subs:
        db.delete(sub)
    if subs:
        db.commit()
        invalidate_cache(db, customer_id)


def invalidate_cache(db: Session, customer_id: str) -> None:
    cache = db.scalar(select(EntitlementsCache).where(EntitlementsCache.customer_id == customer_id))
    if cache:
        db.delete(cache)
        db.commit()
