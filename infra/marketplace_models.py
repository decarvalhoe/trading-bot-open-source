"""SQLAlchemy models powering the marketplace service."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Listing(Base):
    """A strategy that can be published to the marketplace."""

    __tablename__ = "marketplace_listings"

    id: int = Column(Integer, primary_key=True)
    owner_id: str = Column(String(64), nullable=False, index=True)
    strategy_name: str = Column(String(128), nullable=False)
    description: Optional[str] = Column(Text)
    price_cents: int = Column(Integer, nullable=False)
    currency: str = Column(String(3), nullable=False, default="USD")
    connect_account_id: str = Column(String(64), nullable=False)
    status: str = Column(String(16), nullable=False, default="published")
    created_at: datetime = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    versions = relationship(
        "ListingVersion",
        back_populates="listing",
        cascade="all, delete-orphan",
        order_by="ListingVersion.created_at.desc()",
    )
    subscriptions = relationship(
        "MarketplaceSubscription",
        back_populates="listing",
        cascade="all, delete-orphan",
    )


class ListingVersion(Base):
    """Immutable payload representing a published version of a listing."""

    __tablename__ = "marketplace_versions"

    id: int = Column(Integer, primary_key=True)
    listing_id: int = Column(
        Integer,
        ForeignKey("marketplace_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: str = Column(String(32), nullable=False, default="1.0.0")
    changelog: Optional[str] = Column(Text)
    configuration: Dict[str, object] = Column(JSON, nullable=False, default=dict)
    is_published: bool = Column(Boolean, nullable=False, default=True)
    created_at: datetime = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    listing = relationship("Listing", back_populates="versions")

    __table_args__ = (
        UniqueConstraint("listing_id", "version", name="uq_listing_version"),
    )


class MarketplaceSubscription(Base):
    """Represents an investor copying a strategy from the marketplace."""

    __tablename__ = "marketplace_subscriptions"

    id: int = Column(Integer, primary_key=True)
    listing_id: int = Column(
        Integer,
        ForeignKey("marketplace_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscriber_id: str = Column(String(64), nullable=False, index=True)
    version_id: Optional[int] = Column(
        Integer,
        ForeignKey("marketplace_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    payment_reference: Optional[str] = Column(String(128))
    status: str = Column(String(16), nullable=False, default="active")
    created_at: datetime = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    listing = relationship("Listing", back_populates="subscriptions")
    version = relationship("ListingVersion")

    __table_args__ = (
        UniqueConstraint("listing_id", "subscriber_id", name="uq_listing_subscriber"),
    )


__all__ = ["Base", "Listing", "ListingVersion", "MarketplaceSubscription"]
