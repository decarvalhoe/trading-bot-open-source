from __future__ import annotations

import functools

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = Field(
        "sqlite+pysqlite:///./reports.db",
        alias="REPORTS_DATABASE_URL",
    )
    celery_broker_url: str = Field("redis://redis:6379/0", alias="REPORTS_CELERY_BROKER")
    celery_backend_url: str = Field("redis://redis:6379/1", alias="REPORTS_CELERY_BACKEND")
    refresh_interval_seconds: int = Field(300, alias="REPORTS_REFRESH_INTERVAL")

    class Config:
        env_file = ".env"
        case_sensitive = False


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()
