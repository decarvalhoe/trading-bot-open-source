from __future__ import annotations

import functools

from pydantic import Field
from pydantic_settings import BaseSettings


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


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()
