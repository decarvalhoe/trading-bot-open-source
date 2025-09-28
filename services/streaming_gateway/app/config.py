"""Configuration utilities for the streaming gateway service."""

from functools import lru_cache
from typing import List

from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """Runtime configuration loaded from the environment."""

    twitch_client_id: str = Field("", description="OAuth client id for Twitch applications")
    twitch_client_secret: str = Field(
        "", description="OAuth client secret for Twitch applications", repr=False
    )
    youtube_client_id: str = Field("", description="OAuth client id for Google applications")
    youtube_client_secret: str = Field(
        "", description="OAuth client secret for Google applications", repr=False
    )
    youtube_api_key: str = Field(
        "", description="Optional API key used for polling YouTube live chat", repr=False
    )
    discord_client_id: str = Field("", description="Discord application identifier")
    discord_client_secret: str = Field(
        "", description="Discord application secret", repr=False
    )
    discord_bot_token: str = Field(
        "", description="Bot token used to send embeds once the installation flow completed", repr=False
    )
    encryption_key: str = Field(
        "", description="Base64 encoded symmetric key used to encrypt OAuth tokens", repr=False
    )
    overlay_token_secret: str = Field(
        "", description="Secret used to sign short lived overlay access tokens", repr=False
    )
    overlay_token_ttl_seconds: int = Field(300, description="Lifetime of overlay tokens in seconds")
    allowed_origins: List[str] = Field(
        default_factory=lambda: ["https://obsproject.com", "https://studio.obsproject.com"],
        description="Origins allowed to interact with the gateway API",
    )
    public_base_url: str = Field(
        "http://localhost:8000", description="External URL pointing to this service"
    )
    rate_limit_per_minute: int = Field(120, description="Maximum allowed requests per minute per IP")
    redis_url: str = Field("redis://localhost:6379/0", description="Redis URL for stream fan-out")
    nats_url: str = Field("nats://localhost:4222", description="NATS JetStream URL")
    pipeline_backend: str = Field(
        "redis", description="Streaming backend to use (redis|nats)", regex="^(redis|nats)$"
    )
    tradingview_hmac_secret: str = Field(
        "", description="Optional secret used to validate TradingView webhook signatures", repr=False
    )

    class Config:
        env_prefix = "STREAMING_GATEWAY_"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings to avoid re-parsing environment variables."""

    return Settings()
