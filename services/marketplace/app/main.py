"""FastAPI application exposing the marketplace service."""
from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from infra import AuditBase, MarketplaceBase, MarketplaceSubscription
from libs.audit import record_audit
from libs.db.db import engine, get_db
from libs.entitlements.fastapi import install_entitlements_middleware

from .dependencies import (
    get_actor_id,
    get_entitlements,
    require_copy_capability,
    require_publish_capability,
)
from .schemas import CopyRequest, CopyResponse, ListingCreate, ListingOut, ListingVersionRequest
from .service import add_version, create_listing, create_subscription, get_listing, list_listings

app = FastAPI(title="Marketplace Service", version="0.1.0")

MarketplaceBase.metadata.create_all(bind=engine)
AuditBase.metadata.create_all(bind=engine)

install_entitlements_middleware(app)

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
def browse_listings(db: Session = Depends(get_db)):
    listings = list_listings(db)
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


@router.post("/copies", response_model=CopyResponse, status_code=201)
def copy_strategy(
    payload: CopyRequest,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_actor_id),
    _: object = Depends(require_copy_capability),
):
    subscription = create_subscription(db, actor_id=actor_id, payload=payload)
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
