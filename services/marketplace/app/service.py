"""Domain logic for the marketplace API."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from infra import Listing, ListingReview, ListingVersion, MarketplaceSubscription
from libs.audit import record_audit

from .payments import StripeConnectGateway
from .review import ListingStatus, perform_review
from .schemas import CopyRequest, ListingCreate, ListingReviewCreate, ListingVersionRequest


class ListingSortOption(str, Enum):
    NEWEST = "created_desc"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    PERFORMANCE_ASC = "performance_asc"
    PERFORMANCE_DESC = "performance_desc"
    RISK_ASC = "risk_asc"
    RISK_DESC = "risk_desc"
    RATING_DESC = "rating_desc"


@dataclass(slots=True)
class ListingFilters:
    min_performance: Optional[float] = None
    max_risk: Optional[float] = None
    max_price: Optional[int] = None
    search: Optional[str] = None
    sort: ListingSortOption = ListingSortOption.NEWEST


def create_listing(db: Session, *, owner_id: str, payload: ListingCreate) -> Listing:
    listing = Listing(
        owner_id=owner_id,
        strategy_name=payload.strategy_name,
        description=payload.description,
        price_cents=payload.price_cents,
        currency=payload.currency.upper(),
        connect_account_id=payload.connect_account_id,
        performance_score=payload.performance_score,
        risk_score=payload.risk_score,
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

    review_result = perform_review(listing)
    listing.status = review_result.status.value
    listing.review_notes = review_result.summary
    listing.reviewed_at = review_result.executed_at

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
    record_audit(
        db,
        service="marketplace",
        action="listing.review.automated",
        actor_id=owner_id,
        subject_id=str(listing.id),
        details={
            "status": listing.status,
            "notes": review_result.notes,
        },
    )
    db.commit()
    db.refresh(listing)
    return listing


def add_version(
    db: Session, *, listing: Listing, payload: ListingVersionRequest, actor_id: str
) -> ListingVersion:
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


def _with_review_stats(stmt: Select) -> tuple[Select, Any]:
    review_stats = (
        select(
            ListingReview.listing_id.label("listing_id"),
            func.count(ListingReview.id).label("reviews_count"),
            func.avg(ListingReview.rating).label("average_rating"),
        )
        .group_by(ListingReview.listing_id)
        .subquery()
    )
    stmt = stmt.outerjoin(review_stats, review_stats.c.listing_id == Listing.id).add_columns(
        review_stats.c.reviews_count, review_stats.c.average_rating
    )
    return stmt, review_stats


def _attach_review_stats(
    rows: list[tuple[Listing, Optional[int], Optional[float]]]
) -> list[Listing]:
    listings: list[Listing] = []
    for listing, reviews_count, average_rating in rows:
        setattr(listing, "reviews_count", int(reviews_count or 0))
        setattr(
            listing, "average_rating", float(average_rating) if average_rating is not None else None
        )
        listings.append(listing)
    return listings


def list_listings(db: Session, filters: Optional[ListingFilters] = None) -> list[Listing]:
    filters = filters or ListingFilters()
    stmt: Select = (
        select(Listing)
        .where(Listing.status == ListingStatus.APPROVED.value)
        .options(selectinload(Listing.versions))
    )
    stmt, review_stats = _with_review_stats(stmt)

    if filters.min_performance is not None:
        stmt = stmt.where(Listing.performance_score >= filters.min_performance)
    if filters.max_risk is not None:
        stmt = stmt.where(Listing.risk_score <= filters.max_risk)
    if filters.max_price is not None:
        stmt = stmt.where(Listing.price_cents <= filters.max_price)
    if filters.search:
        search_term = filters.search.strip().lower()
        if search_term:
            like_expr = f"%{search_term}%"
            stmt = stmt.where(func.lower(Listing.strategy_name).like(like_expr))

    sort_value = filters.sort
    if sort_value == ListingSortOption.PRICE_ASC:
        stmt = stmt.order_by(Listing.price_cents.asc(), Listing.created_at.desc())
    elif sort_value == ListingSortOption.PRICE_DESC:
        stmt = stmt.order_by(Listing.price_cents.desc(), Listing.created_at.desc())
    elif sort_value == ListingSortOption.PERFORMANCE_ASC:
        stmt = stmt.order_by(
            func.coalesce(Listing.performance_score, 1e9).asc(),
            Listing.created_at.desc(),
        )
    elif sort_value == ListingSortOption.PERFORMANCE_DESC:
        stmt = stmt.order_by(
            func.coalesce(Listing.performance_score, -1).desc(),
            Listing.created_at.desc(),
        )
    elif sort_value == ListingSortOption.RISK_ASC:
        stmt = stmt.order_by(
            func.coalesce(Listing.risk_score, 1e9).asc(),
            Listing.created_at.desc(),
        )
    elif sort_value == ListingSortOption.RISK_DESC:
        stmt = stmt.order_by(
            func.coalesce(Listing.risk_score, -1).desc(),
            Listing.created_at.desc(),
        )
    elif sort_value == ListingSortOption.RATING_DESC:
        stmt = stmt.order_by(
            func.coalesce(review_stats.c.average_rating, 0).desc(),
            Listing.created_at.desc(),
        )
    else:
        stmt = stmt.order_by(Listing.created_at.desc())

    result = db.execute(stmt).all()
    return _attach_review_stats(result)


def get_listing(db: Session, listing_id: int) -> Listing:
    stmt: Select = (
        select(Listing).where(Listing.id == listing_id).options(selectinload(Listing.versions))
    )
    stmt, _ = _with_review_stats(stmt)
    row = db.execute(stmt).first()
    if not row:
        raise HTTPException(status_code=404, detail="Listing not found")
    listing, reviews_count, average_rating = row
    return _attach_review_stats([(listing, reviews_count, average_rating)])[0]


def serialize_subscription(subscription: MarketplaceSubscription) -> dict[str, object]:
    listing = subscription.listing
    return {
        "id": subscription.id,
        "listing_id": subscription.listing_id,
        "subscriber_id": subscription.subscriber_id,
        "version_id": subscription.version_id,
        "payment_reference": subscription.payment_reference,
        "connect_transfer_reference": subscription.connect_transfer_reference,
        "status": subscription.status,
        "leverage": subscription.leverage,
        "allocated_capital": subscription.allocated_capital,
        "risk_limits": subscription.risk_limits or {},
        "replication_status": subscription.replication_status,
        "divergence_bps": subscription.divergence_bps,
        "total_fees_paid": subscription.total_fees_paid or 0.0,
        "last_synced_at": subscription.last_synced_at,
        "strategy_name": listing.strategy_name if listing else None,
        "leader_id": listing.owner_id if listing else None,
        "created_at": subscription.created_at,
    }


def create_subscription(
    db: Session,
    *,
    actor_id: str,
    payload: CopyRequest,
    payments_gateway: StripeConnectGateway | None = None,
) -> MarketplaceSubscription:
    listing = get_listing(db, payload.listing_id)

    if listing.owner_id == actor_id:
        raise HTTPException(
            status_code=400, detail="Creators cannot subscribe to their own strategy"
        )
    if listing.status != ListingStatus.APPROVED.value:
        raise HTTPException(status_code=403, detail="Listing is not approved for subscription")

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

    payment_reference = payload.payment_reference
    connect_transfer_reference: Optional[str] = None
    status = "pending"
    if not payment_reference and payments_gateway and payments_gateway.is_configured:
        payment_result = payments_gateway.create_subscription(
            listing,
            subscriber_id=actor_id,
        )
        payment_reference = payment_result.reference
        connect_transfer_reference = payment_result.transfer_reference
        status = payment_result.status
    elif payment_reference:
        status = "active"

    if existing:
        subscription = existing
        subscription.version = version
        subscription.payment_reference = payment_reference
        subscription.connect_transfer_reference = connect_transfer_reference
        subscription.status = status
    else:
        subscription = MarketplaceSubscription(
            listing=listing,
            subscriber_id=actor_id,
            version=version,
            payment_reference=payment_reference,
            connect_transfer_reference=connect_transfer_reference,
            status=status,
        )
        db.add(subscription)

    subscription.leverage = payload.leverage
    subscription.allocated_capital = payload.allocated_capital
    subscription.risk_limits = payload.risk_limits or {}
    subscription.replication_status = "pending"
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
            "payment_reference": payment_reference,
            "status": subscription.status,
        },
    )
    db.commit()
    db.refresh(subscription)
    return subscription


def list_reviews(db: Session, listing_id: int) -> list[ListingReview]:
    stmt = (
        select(ListingReview)
        .where(ListingReview.listing_id == listing_id)
        .order_by(ListingReview.created_at.desc())
    )
    return db.scalars(stmt).all()


def create_or_update_review(
    db: Session,
    *,
    listing: Listing,
    reviewer_id: str,
    payload: ListingReviewCreate,
) -> ListingReview:
    review = db.scalar(
        select(ListingReview).where(
            ListingReview.listing_id == listing.id,
            ListingReview.reviewer_id == reviewer_id,
        )
    )
    created = False
    if review:
        review.rating = payload.rating
        review.comment = payload.comment
    else:
        review = ListingReview(
            listing=listing,
            reviewer_id=reviewer_id,
            rating=payload.rating,
            comment=payload.comment,
        )
        db.add(review)
        created = True

    record_audit(
        db,
        service="marketplace",
        action="listing.reviewed" if created else "listing.review.updated",
        actor_id=reviewer_id,
        subject_id=str(listing.id),
        details={"rating": payload.rating},
    )
    db.commit()
    db.refresh(review)
    return review
