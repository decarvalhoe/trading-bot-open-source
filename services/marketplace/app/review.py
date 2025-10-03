"""Automated review workflow for marketplace listings."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List

from infra import Listing


class ListingStatus(str, Enum):
    """States used during the validation workflow."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(slots=True)
class ReviewResult:
    """Outcome of automated checks run against a listing."""

    status: ListingStatus
    notes: List[str] = field(default_factory=list)
    executed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def summary(self) -> str:
        if not self.notes:
            return "All automated checks passed"
        return "\n".join(self.notes)


class AutomatedReviewer:
    """Simple rule-based reviewer running deterministic checks."""

    def review(self, listing: Listing) -> ReviewResult:
        notes: list[str] = []
        if listing.price_cents <= 0:
            notes.append("Price must be greater than zero for a paid subscription")
        if not listing.connect_account_id.startswith("acct_"):
            notes.append("Stripe Connect account id must start with 'acct_'")
        if listing.risk_score is not None and listing.risk_score > 10:
            notes.append("Risk score must be below or equal to 10")
        status = ListingStatus.REJECTED if notes else ListingStatus.APPROVED
        return ReviewResult(status=status, notes=notes)


def perform_review(listing: Listing, *, reviewer: AutomatedReviewer | None = None) -> ReviewResult:
    """Run the automated reviewer against a listing instance."""

    reviewer = reviewer or AutomatedReviewer()
    return reviewer.review(listing)


__all__ = ["AutomatedReviewer", "ListingStatus", "ReviewResult", "perform_review"]
