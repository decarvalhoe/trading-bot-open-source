"""FastAPI application exposing the marketplace service."""
from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from infra import AuditBase, MarketplaceBase, MarketplaceSubscription
from libs.audit import record_audit
from libs.db.db import engine, get_db
from libs.entitlements.fastapi import install_entitlements_middleware
from libs.observability.logging import RequestContextMiddleware, configure_logging
from libs.observability.metrics import setup_metrics

from .dependencies import (
    get_actor_id,
    get_entitlements,
    get_payments_gateway,
    require_copy_capability,
    require_publish_capability,
)
from .payments import StripeConnectGateway
from .schemas import (
    CopyRequest,
    CopyResponse,
    ListingCreate,
    ListingOut,
    ListingReviewCreate,
    ListingReviewOut,
    ListingVersionRequest,
)
from .service import (
    ListingFilters,
    ListingSortOption,
    add_version,
    create_listing,
    create_or_update_review,
    create_subscription,
    get_listing,
    list_listings,
    list_reviews,
)

configure_logging("marketplace")

app = FastAPI(title="Marketplace Service", version="0.1.0")

MarketplaceBase.metadata.create_all(bind=engine)
AuditBase.metadata.create_all(bind=engine)

install_entitlements_middleware(app)
app.add_middleware(RequestContextMiddleware, service_name="marketplace")
setup_metrics(app, service_name="marketplace")

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


@router.post("/listings", response_model=ListingOut, status_code=201)
def publish_listing(
    payload: ListingCreate,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_actor_id),
    _: object = Depends(require_publish_capability),
):
    listing = create_listing(db, owner_id=actor_id, payload=payload)
    return ListingOut.model_validate(listing)


@router.get("/listings", response_model=list[ListingOut])
def browse_listings(
    db: Session = Depends(get_db),
    min_performance: float | None = Query(default=None, ge=0),
    max_risk: float | None = Query(default=None, ge=0),
    max_price: int | None = Query(default=None, ge=0),
    search: str | None = Query(default=None, min_length=1),
    sort: ListingSortOption = Query(default=ListingSortOption.NEWEST),
):
    filters = ListingFilters(
        min_performance=min_performance,
        max_risk=max_risk,
        max_price=max_price,
        search=search,
        sort=sort,
    )
    listings = list_listings(db, filters=filters)
    return [ListingOut.model_validate(obj) for obj in listings]


@router.post("/listings/{listing_id}/versions", response_model=ListingOut)
def publish_version(
    listing_id: int,
    payload: ListingVersionRequest,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_actor_id),
    _: object = Depends(require_publish_capability),
):
    listing = get_listing(db, listing_id)
    add_version(db, listing=listing, payload=payload, actor_id=actor_id)
    db.refresh(listing)
    return ListingOut.model_validate(listing)


@router.get("/listings/{listing_id}", response_model=ListingOut)
def retrieve_listing(listing_id: int, db: Session = Depends(get_db)):
    listing = get_listing(db, listing_id)
    return ListingOut.model_validate(listing)


@router.get("/listings/{listing_id}/reviews", response_model=list[ListingReviewOut])
def browse_reviews(listing_id: int, db: Session = Depends(get_db)):
    get_listing(db, listing_id)
    reviews = list_reviews(db, listing_id)
    return [ListingReviewOut.model_validate(obj) for obj in reviews]


@router.post("/listings/{listing_id}/reviews", response_model=ListingReviewOut, status_code=201)
def submit_review(
    listing_id: int,
    payload: ListingReviewCreate,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_actor_id),
    _: object = Depends(get_entitlements),
):
    listing = get_listing(db, listing_id)
    review = create_or_update_review(db, listing=listing, reviewer_id=actor_id, payload=payload)
    return ListingReviewOut.model_validate(review)


@router.post("/copies", response_model=CopyResponse, status_code=201)
def copy_strategy(
    payload: CopyRequest,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_actor_id),
    _: object = Depends(require_copy_capability),
    payments_gateway: StripeConnectGateway = Depends(get_payments_gateway),
):
    subscription = create_subscription(
        db,
        actor_id=actor_id,
        payload=payload,
        payments_gateway=payments_gateway,
    )
    return CopyResponse.model_validate(subscription)


@router.get("/copies", response_model=list[CopyResponse])
def my_copies(
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_actor_id),
    _: object = Depends(get_entitlements),
):
    stmt = select(MarketplaceSubscription).where(MarketplaceSubscription.subscriber_id == actor_id)
    subscriptions = db.scalars(stmt).all()
    for sub in subscriptions:
        record_audit(
            db,
            service="marketplace",
            action="listing.copy.viewed",
            actor_id=actor_id,
            subject_id=str(sub.listing_id),
            details={"subscription_id": sub.id},
        )
    db.commit()
    return [CopyResponse.model_validate(sub) for sub in subscriptions]


app.include_router(router)


@app.get("/health")
def healthcheck():
    return {"status": "ok"}
