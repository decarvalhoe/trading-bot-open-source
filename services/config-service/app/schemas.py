from pydantic import AnyUrl, BaseModel


class ConfigUpdate(BaseModel):
    APP_NAME: str | None = None
    ENVIRONMENT: str | None = None
    POSTGRES_DSN: str | None = None
    REDIS_URL: AnyUrl | str | None = None
    RABBITMQ_URL: AnyUrl | str | None = None
