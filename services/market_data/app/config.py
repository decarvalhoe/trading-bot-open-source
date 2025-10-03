from __future__ import annotations

import functools

import os

from pydantic import Field
from pydantic_settings import BaseSettings

from libs.secrets import get_secret
from libs.env import DEFAULT_POSTGRES_DSN_NATIVE


def _default_database_url() -> str:
    for env_var in ("MARKET_DATA_DATABASE_URL", "DATABASE_URL", "POSTGRES_DSN"):
        value = os.getenv(env_var)
        if value:
            return value
    return DEFAULT_POSTGRES_DSN_NATIVE


class Settings(BaseSettings):
    database_url: str = Field(
        default_factory=_default_database_url,
        alias="MARKET_DATA_DATABASE_URL",
    )
    tradingview_hmac_secret: str = Field(..., alias="TRADINGVIEW_HMAC_SECRET")
    binance_api_key: str | None = Field(None, alias="BINANCE_API_KEY")
    binance_api_secret: str | None = Field(None, alias="BINANCE_API_SECRET")
    ibkr_host: str = Field("127.0.0.1", alias="IBKR_HOST")
    ibkr_port: int = Field(4001, alias="IBKR_PORT")
    ibkr_client_id: int = Field(1, alias="IBKR_CLIENT_ID")
    topstep_base_url: str = Field("https://api.topstep.com", alias="TOPSTEP_BASE_URL")
    topstep_client_id: str | None = Field(None, alias="TOPSTEP_CLIENT_ID")
    topstep_client_secret: str | None = Field(None, alias="TOPSTEP_CLIENT_SECRET")

    class Config:
        env_file = ".env"
        case_sensitive = False


_SECRET_KEYS = [
    "MARKET_DATA_DATABASE_URL",
    "TRADINGVIEW_HMAC_SECRET",
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
    "TOPSTEP_CLIENT_ID",
    "TOPSTEP_CLIENT_SECRET",
]


def _secret_overrides() -> dict[str, str]:
    overrides: dict[str, str] = {}
    for key in _SECRET_KEYS:
        value = get_secret(key)
        if value is not None:
            overrides[key] = value
    return overrides


@functools.lru_cache
def get_settings() -> Settings:
    return Settings(**_secret_overrides())
