from __future__ import annotations

import functools

from pydantic import Field
from pydantic_settings import BaseSettings

from libs.env import get_redis_url


def _default_celery_broker_url() -> str:
    return get_redis_url(env_var="REPORTS_CELERY_BROKER", database=0)


def _default_celery_backend_url() -> str:
    return get_redis_url(env_var="REPORTS_CELERY_BACKEND", database=1)


class Settings(BaseSettings):
    database_url: str = Field(
        "sqlite+pysqlite:///./reports.db",
        alias="REPORTS_DATABASE_URL",
    )
    celery_broker_url: str = Field(
        default_factory=_default_celery_broker_url,
        alias="REPORTS_CELERY_BROKER",
    )
    celery_backend_url: str = Field(
        default_factory=_default_celery_backend_url,
        alias="REPORTS_CELERY_BACKEND",
    )
    refresh_interval_seconds: int = Field(300, alias="REPORTS_REFRESH_INTERVAL")
    reports_storage_path: str = Field("./generated-reports", alias="REPORTS_STORAGE_PATH")

    class Config:
        env_file = ".env"
        case_sensitive = False


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()
