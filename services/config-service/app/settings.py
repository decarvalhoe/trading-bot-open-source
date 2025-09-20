from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .persistence import read_config_for_env


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.dev", env_prefix="", case_sensitive=False, extra="allow"
    )

    APP_NAME: str = "trading-bot-config"
    ENVIRONMENT: str = Field(default="dev", pattern="^(dev|test|prod)$")
    POSTGRES_DSN: str = "postgresql+psycopg2://trading:trading@postgres:5432/trading"
    REDIS_URL: AnyUrl | str = "redis://redis:6379/0"
    RABBITMQ_URL: AnyUrl | str = "amqp://guest:guest@rabbitmq:5672//"


def load_settings() -> Settings:
    env_settings = Settings()
    file_data = read_config_for_env(env_settings.ENVIRONMENT)
    if file_data:
        merged_data = {**env_settings.model_dump(), **file_data}
        return Settings(**merged_data)
    return env_settings
