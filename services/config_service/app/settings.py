from __future__ import annotations

import os
from pathlib import Path

from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from libs.env import (
    DEFAULT_POSTGRES_DSN_NATIVE,
    get_environment,
    get_rabbitmq_url,
    get_redis_url,
)

from .persistence import read_config_for_env


ENV_FILE_MAP = {
    "dev": ".env.dev",
    "test": ".env.test",
    "prod": ".env.prod",
    "native": ".env.native",
}


def _default_postgres_dsn() -> str:
    for env_var in ("POSTGRES_DSN", "DATABASE_URL"):
        value = os.getenv(env_var)
        if value:
            return value
    return DEFAULT_POSTGRES_DSN_NATIVE


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.dev", env_prefix="", case_sensitive=False, extra="allow"
    )

    APP_NAME: str = "trading-bot-config"
    ENVIRONMENT: str = Field(default_factory=get_environment, pattern="^(dev|test|prod|native)$")
    POSTGRES_DSN: str = Field(default_factory=_default_postgres_dsn)
    REDIS_URL: AnyUrl | str = Field(default_factory=get_redis_url)
    RABBITMQ_URL: AnyUrl | str = Field(default_factory=get_rabbitmq_url)


def load_settings() -> Settings:
    env_name = get_environment()
    env_file = ENV_FILE_MAP.get(env_name)
    settings_kwargs = {}
    if env_file and Path(env_file).exists():
        settings_kwargs["_env_file"] = env_file

    env_settings = Settings(**settings_kwargs)
    file_data = read_config_for_env(env_settings.ENVIRONMENT)

    merged_data = {
        **env_settings.model_dump(),
        **(file_data or {}),
    }
    merged_data.setdefault("ENVIRONMENT", env_settings.ENVIRONMENT)
    merged_data.setdefault("POSTGRES_DSN", _default_postgres_dsn())
    merged_data.setdefault("REDIS_URL", get_redis_url())
    merged_data.setdefault("RABBITMQ_URL", get_rabbitmq_url())

    return Settings(**merged_data)
