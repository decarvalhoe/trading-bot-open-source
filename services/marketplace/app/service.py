"""Domain logic for the marketplace API."""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from infra import Listing, ListingVersion, MarketplaceSubscription
from libs.audit import record_audit

from .schemas import CopyRequest, ListingCreate, ListingVersionRequest


def create_listing(db: Session, *, owner_id: str, payload: ListingCreate) -> Listing:
    listing = Listing(
        owner_id=owner_id,
        strategy_name=payload.strategy_name,
        description=payload.description,
        price_cents=payload.price_cents,
        currency=payload.currency.upper(),
        connect_account_id=payload.connect_account_id,
    )
    db.add(listing)
    db.flush()

    if payload.initial_version:
        version_payload = payload.initial_version
        listing.versions.append(
            ListingVersion(
                version=version_payload.version,
                configuration=version_payload.configuration,
                changelog=version_payload.changelog,
            )
        )

    record_audit(
        db,
        service="marketplace",
        action="listing.created",
        actor_id=owner_id,
        subject_id=str(listing.id),
        details={
            "strategy_name": listing.strategy_name,
            "price_cents": listing.price_cents,
            "currency": listing.currency,
        },
    )
    db.commit()
    db.refresh(listing)
    return listing


def add_version(db: Session, *, listing: Listing, payload: ListingVersionRequest, actor_id: str) -> ListingVersion:
    if listing.owner_id != actor_id:
        raise HTTPException(status_code=403, detail="Only the owner can publish a new version")

    version = ListingVersion(
        listing=listing,
        version=payload.version,
        configuration=payload.configuration,
        changelog=payload.changelog,
    )
    db.add(version)
    db.flush()

    record_audit(
        db,
        service="marketplace",
        action="listing.version.published",
        actor_id=actor_id,
        subject_id=str(listing.id),
        details={"version": version.version},
    )
    db.commit()
    db.refresh(version)
    return version


def list_listings(db: Session) -> list[Listing]:
    stmt = select(Listing).options(selectinload(Listing.versions)).order_by(Listing.created_at.desc())
    return db.scalars(stmt).all()


def get_listing(db: Session, listing_id: int) -> Listing:
    listing = db.scalar(
        select(Listing)
        .where(Listing.id == listing_id)
        .options(selectinload(Listing.versions))
    )
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


def create_subscription(
    db: Session,
    *,
    actor_id: str,
    payload: CopyRequest,
) -> MarketplaceSubscription:
    listing = get_listing(db, payload.listing_id)

    if listing.owner_id == actor_id:
        raise HTTPException(status_code=400, detail="Creators cannot subscribe to their own strategy")

    existing = db.scalar(
        select(MarketplaceSubscription).where(
            MarketplaceSubscription.listing_id == payload.listing_id,
            MarketplaceSubscription.subscriber_id == actor_id,
        )
    )
    if existing and existing.status == "active":
        raise HTTPException(status_code=409, detail="Subscription already active")

    version: Optional[ListingVersion] = None
    if payload.version_id:
        version = db.get(ListingVersion, payload.version_id)
        if not version or version.listing_id != listing.id:
            raise HTTPException(status_code=400, detail="Version does not belong to listing")
    else:
        version = listing.versions[0] if listing.versions else None

    subscription = MarketplaceSubscription(
        listing=listing,
        subscriber_id=actor_id,
        version=version,
        payment_reference=payload.payment_reference,
    )
    db.add(subscription)
    db.flush()

    record_audit(
        db,
        service="marketplace",
        action="listing.copied",
        actor_id=actor_id,
        subject_id=str(listing.id),
        details={
            "subscription_id": subscription.id,
            "version_id": subscription.version_id,
            "payment_reference": payload.payment_reference,
        },
    )
    db.commit()
    db.refresh(subscription)
    return subscription
