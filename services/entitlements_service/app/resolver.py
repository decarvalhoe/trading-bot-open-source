from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from infra import EntitlementsCache, Feature, Plan, Subscription

CACHE_TTL = timedelta(minutes=5)


def _build_cache_payload(plan: Plan) -> Dict[str, Dict[str, Optional[int]]]:
    capabilities: Dict[str, bool] = {}
    quotas: Dict[str, Optional[int]] = {}
    for association in plan.features:
        feature: Feature = association.feature
        if feature.kind == "quota":
            quotas[feature.code] = association.limit
        else:
            capabilities[feature.code] = True
    return {"capabilities": capabilities, "quotas": quotas}


def resolve_entitlements(db: Session, customer_id: str) -> Dict[str, object]:
    cache = db.scalar(select(EntitlementsCache).where(EntitlementsCache.customer_id == customer_id))
    if cache and cache.refreshed_at >= datetime.utcnow() - CACHE_TTL:
        return {"customer_id": customer_id, **cache.data, "cached_at": cache.refreshed_at}

    subscription = db.scalar(
        select(Subscription)
        .join(Plan, Plan.id == Subscription.plan_id)
        .where(Subscription.customer_id == customer_id, Subscription.status == "active")
    )
    if not subscription or not subscription.plan:
        payload = {"capabilities": {}, "quotas": {}}
        _store_cache(db, customer_id, payload)
        return {"customer_id": customer_id, **payload, "cached_at": None}

    payload = _build_cache_payload(subscription.plan)
    _store_cache(db, customer_id, payload)
    return {"customer_id": customer_id, **payload, "cached_at": datetime.utcnow()}


def _store_cache(db: Session, customer_id: str, payload: Dict[str, Dict[str, Optional[int]]]) -> None:
    cache = db.scalar(select(EntitlementsCache).where(EntitlementsCache.customer_id == customer_id))
    now = datetime.utcnow()
    if cache:
        cache.data = payload
        cache.refreshed_at = now
    else:
        cache = EntitlementsCache(customer_id=customer_id, data=payload, refreshed_at=now)
        db.add(cache)
    db.commit()
