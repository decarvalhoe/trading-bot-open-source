"""SQLAlchemy models describing billing and entitlements storage."""
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
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Plan(Base):
    """Commercial plan exposed through Stripe."""

    __tablename__ = "plans"

    id: int = Column(Integer, primary_key=True)
    code: str = Column(String(64), unique=True, nullable=False)
    name: str = Column(String(128), nullable=False)
    stripe_price_id: str = Column(String(128), unique=True, nullable=False)
    description: Optional[str] = Column(String(255))
    billing_interval: str = Column(
        String(16), nullable=False, server_default=text("monthly"), default="monthly"
    )
    trial_period_days: Optional[int] = Column(Integer)
    active: bool = Column(Boolean, nullable=False, server_default=text("true"))

    features = relationship("PlanFeature", back_populates="plan", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="plan")


class Feature(Base):
    """Feature flag or quota entry."""

    __tablename__ = "features"

    id: int = Column(Integer, primary_key=True)
    code: str = Column(String(64), unique=True, nullable=False)
    name: str = Column(String(128), nullable=False)
    kind: str = Column(String(16), nullable=False, default="capability")  # capability|quota
    description: Optional[str] = Column(String(255))

    plans = relationship("PlanFeature", back_populates="feature", cascade="all, delete-orphan")


class PlanFeature(Base):
    """Association between plan and feature with optional limit."""

    __tablename__ = "plan_features"

    id: int = Column(Integer, primary_key=True)
    plan_id: int = Column(Integer, ForeignKey("plans.id", ondelete="CASCADE"), nullable=False)
    feature_id: int = Column(Integer, ForeignKey("features.id", ondelete="CASCADE"), nullable=False)
    limit: Optional[int] = Column(Integer)

    plan = relationship("Plan", back_populates="features")
    feature = relationship("Feature", back_populates="plans")

    __table_args__ = (UniqueConstraint("plan_id", "feature_id", name="uq_plan_feature"),)


class Subscription(Base):
    """Customer subscription resolved from Stripe."""

    __tablename__ = "subscriptions"

    id: int = Column(Integer, primary_key=True)
    customer_id: str = Column(String(64), nullable=False, index=True)
    plan_id: int = Column(Integer, ForeignKey("plans.id", ondelete="SET NULL"))
    status: str = Column(String(32), nullable=False)
    current_period_end: Optional[datetime] = Column(DateTime(timezone=True))
    trial_end: Optional[datetime] = Column(DateTime(timezone=True))
    connect_account_id: Optional[str] = Column(String(64))
    payment_reference: Optional[str] = Column(String(128))

    plan = relationship("Plan", back_populates="subscriptions")

    __table_args__ = (UniqueConstraint("customer_id", "status", name="uq_subscription_customer_status"),)


class EntitlementsCache(Base):
    """Cached JSON payload served by the entitlements API."""

    __tablename__ = "entitlements_cache"

    id: int = Column(Integer, primary_key=True)
    customer_id: str = Column(String(64), unique=True, nullable=False)
    data: Dict[str, object] = Column(JSON, nullable=False)
    refreshed_at: datetime = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


__all__ = [
    "Base",
    "Plan",
    "Feature",
    "PlanFeature",
    "Subscription",
    "EntitlementsCache",
]
