from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration du service de streaming."""

    app_name: str = "streaming"
    pipeline_backend: Literal["memory", "redis", "nats"] = Field(
        "memory",
        description="Backend utilisé pour diffuser les événements (Redis Streams, NATS JetStream ou mémoire).",
    )
    redis_url: str = Field("redis://localhost:6379/0", description="URL du serveur Redis")
    nats_url: str = Field("nats://localhost:4222", description="URL du cluster NATS")
    service_token_reports: str | None = Field(
        None,
        description="Jeton partagé autorisant le service reports à pousser des événements.",
    )
    service_token_inplay: str | None = Field(
        None,
        description="Jeton partagé autorisant le service inplay à pousser des événements.",
    )
    entitlements_capability: str = Field(
        "can.stream_public",
        description="Capacité requise pour consommer les flux publics.",
    )

    class Config:
        env_prefix = "STREAMING_"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


__all__ = ["Settings", "get_settings"]
