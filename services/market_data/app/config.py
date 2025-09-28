from __future__ import annotations

import functools

from pydantic import Field
from pydantic_settings import BaseSettings

from libs.secrets import get_secret


class Settings(BaseSettings):
    database_url: str = Field(
        "postgresql+psycopg2://trading:trading@postgres:5432/trading",
        alias="MARKET_DATA_DATABASE_URL",
    )
    tradingview_hmac_secret: str = Field(..., alias="TRADINGVIEW_HMAC_SECRET")
    binance_api_key: str | None = Field(None, alias="BINANCE_API_KEY")
    binance_api_secret: str | None = Field(None, alias="BINANCE_API_SECRET")
    ibkr_host: str = Field("127.0.0.1", alias="IBKR_HOST")
    ibkr_port: int = Field(4001, alias="IBKR_PORT")
    ibkr_client_id: int = Field(1, alias="IBKR_CLIENT_ID")

    class Config:
        env_file = ".env"
        case_sensitive = False


_SECRET_KEYS = [
    "MARKET_DATA_DATABASE_URL",
    "TRADINGVIEW_HMAC_SECRET",
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
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
