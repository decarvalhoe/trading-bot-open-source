"""Environment configuration for the Codex gateway."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settings loaded from environment variables."""

    github_webhook_secret: str = Field(
        "", description="Secret used to validate GitHub webhook signatures", repr=False
    )
    stripe_webhook_secret: str = Field(
        "", description="Secret used to validate Stripe webhook signatures", repr=False
    )
    tradingview_webhook_secret: str = Field(
        "", description="Secret used to validate TradingView webhook signatures", repr=False
    )
    broker_backend: str = Field(
        "memory",
        description="Messaging backend to publish events (memory|redis|sqs)",
    )
    service_name: str = Field("codex-gateway", description="Service identifier used for logging")

    class Config:
        env_prefix = "CODEX_GATEWAY_"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings to avoid re-parsing environment variables."""

    return Settings()
