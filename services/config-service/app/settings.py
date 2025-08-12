from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, AnyUrl, Field
import os
from .persistence import read_config_for_env

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", case_sensitive=False)

    APP_NAME: str = "trading-bot-config"
    ENVIRONMENT: str = Field(default="dev", pattern="^(dev|test|prod)$")
    POSTGRES_DSN: str = "postgresql+psycopg2://trading:trading@postgres:5432/trading"
    REDIS_URL: AnyUrl | str = "redis://redis:6379/0"
    RABBITMQ_URL: AnyUrl | str = "amqp://guest:guest@rabbitmq:5672//"

def load_settings() -> Settings:
    # 1) Base from env
    env_settings = Settings()

    # 2) Merge with file-level overrides (by env)
    file_data = read_config_for_env(env_settings.ENVIRONMENT)
    if file_data:
        merged = {**env_settings.model_dump(), **file_data}
        return Settings(**merged)
    return env_settings
