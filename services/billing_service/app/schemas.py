"""Pydantic models for the billing service."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class FeatureIn(BaseModel):
    code: str = Field(..., description="Internal identifier such as can.use_ibkr")
    name: str
    kind: str = Field(default="capability")
    description: Optional[str] = None


class PlanIn(BaseModel):
    code: str
    name: str
    stripe_price_id: str
    description: Optional[str] = None
    billing_interval: Literal["monthly", "annual"] = Field(default="monthly")
    trial_period_days: Optional[int] = Field(default=None, ge=0)


class PlanFeatureIn(BaseModel):
    plan_code: str
    feature_code: str
    limit: Optional[int] = None


class SubscriptionUpdate(BaseModel):
    customer_id: str
    plan_code: str
    status: str
    current_period_end: Optional[datetime] = None
