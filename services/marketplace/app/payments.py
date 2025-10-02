"""Stripe Connect integration helpers for marketplace subscriptions."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Protocol

from infra import Listing


@dataclass(slots=True)
class StripeSettings:
    """Configuration for Stripe Connect integration."""

    api_key: Optional[str]
    application_fee_percent: Optional[float] = None

    @classmethod
    def from_env(cls) -> StripeSettings:
        api_key = os.getenv("STRIPE_API_KEY")
        fee = os.getenv("STRIPE_APPLICATION_FEE_PERCENT")
        return cls(api_key=api_key, application_fee_percent=float(fee) if fee else None)


@dataclass(slots=True)
class StripeSubscriptionRequest:
    listing_id: int
    price_cents: int
    currency: str
    connect_account_id: str
    subscriber_id: str
    trial_period_days: Optional[int] = None


@dataclass(slots=True)
class StripeSubscriptionResult:
    reference: str
    status: str
    transfer_reference: Optional[str] = None


class StripeClient(Protocol):
    def create_subscription(self, request: StripeSubscriptionRequest) -> StripeSubscriptionResult:
        """Create a subscription on Stripe and return its identifiers."""


class StripeAPIClient:
    """Placeholder Stripe client raising when configuration is missing."""

    def __init__(self, settings: StripeSettings) -> None:
        self.settings = settings

    def create_subscription(
        self, request: StripeSubscriptionRequest
    ) -> StripeSubscriptionResult:  # pragma: no cover - requires real Stripe
        raise RuntimeError("Stripe API client is not configured for this environment")


class StripeConnectGateway:
    """High level facade orchestrating subscription creation with Stripe Connect."""

    def __init__(
        self,
        settings: StripeSettings | None = None,
        client: StripeClient | None = None,
    ) -> None:
        self.settings = settings or StripeSettings.from_env()
        self._client = client or StripeAPIClient(self.settings)

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.api_key)

    def create_subscription(
        self,
        listing: Listing,
        *,
        subscriber_id: str,
        trial_period_days: Optional[int] = None,
    ) -> StripeSubscriptionResult:
        if not self.is_configured:
            raise RuntimeError("Stripe Connect integration is not configured")
        request = StripeSubscriptionRequest(
            listing_id=listing.id,
            price_cents=listing.price_cents,
            currency=listing.currency,
            connect_account_id=listing.connect_account_id,
            subscriber_id=subscriber_id,
            trial_period_days=trial_period_days,
        )
        return self._client.create_subscription(request)


__all__ = [
    "StripeAPIClient",
    "StripeClient",
    "StripeConnectGateway",
    "StripeSettings",
    "StripeSubscriptionRequest",
    "StripeSubscriptionResult",
]
