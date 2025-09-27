from __future__ import annotations

import functools
from typing import Dict, List

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = Field("redis://redis:6379/0", alias="INPLAY_REDIS_URL")
    watchlists: Dict[str, List[str]] = Field(
        default_factory=lambda: {
            "momentum": ["AAPL", "MSFT", "TSLA"],
            "futures": ["ES", "NQ"],
        },
        alias="INPLAY_WATCHLISTS",
    )

    class Config:
        env_file = ".env"
        case_sensitive = False


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()
