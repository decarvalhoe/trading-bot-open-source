from __future__ import annotations

import functools
from typing import Dict, List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from libs.env import get_redis_url


def _default_redis_url() -> str:
    return get_redis_url(env_var="INPLAY_REDIS_URL")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        populate_by_name=True,
    )

    redis_url: str = Field(default_factory=_default_redis_url, alias="INPLAY_REDIS_URL")
    watchlists: Dict[str, List[str]] = Field(
        default_factory=lambda: {
            "momentum": ["AAPL", "MSFT", "TSLA"],
            "futures": ["ES", "NQ"],
        },
        alias="INPLAY_WATCHLISTS",
    )
    reports_base_url: str = Field(
        "http://reports:8000/",
        alias="INPLAY_REPORTS_BASE_URL",
        description="Base URL du service reports-service",
    )
    reports_timeout_seconds: float = Field(
        5.0,
        alias="INPLAY_REPORTS_TIMEOUT_SECONDS",
        description="Délai d'expiration pour les appels au reports-service",
    )
    market_data_base_url: str = Field(
        "http://market-data:8000/",
        alias="INPLAY_MARKET_DATA_BASE_URL",
        description="Base URL du service market-data",
    )
    market_data_timeout_seconds: float = Field(
        5.0,
        alias="INPLAY_MARKET_DATA_TIMEOUT_SECONDS",
        description="Délai d'expiration pour les appels au market-data service",
    )


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()
