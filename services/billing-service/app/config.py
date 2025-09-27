"""Settings for the billing service."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    stripe_api_key: str
    stripe_webhook_secret: str

    @classmethod
    def load(cls) -> "Settings":
        api_key = os.getenv("STRIPE_API_KEY", "test_stripe_api_key")
        webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
        return cls(stripe_api_key=api_key, stripe_webhook_secret=webhook_secret)


settings = Settings.load()
