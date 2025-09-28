"""Environment configuration for the notification service."""

from __future__ import annotations

from functools import lru_cache

from pydantic import EmailStr, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settings loaded from environment variables."""

    service_name: str = Field("notification-service", description="Service identifier")
    http_timeout: float = Field(5.0, description="Timeout for outbound webhook requests")
    slack_default_webhook: str = Field(
        "",
        description="Fallback webhook used when Slack channel target omits an URL",
        repr=False,
    )
    smtp_host: str = Field("localhost", description="SMTP server host for email delivery")
    smtp_port: int = Field(25, description="SMTP server port")
    smtp_sender: EmailStr | None = Field(
        None, description="Email address used as sender when sending email notifications"
    )
    dry_run: bool = Field(
        True,
        description="When enabled the dispatcher logs messages instead of contacting external services",
    )

    class Config:
        env_prefix = "NOTIFICATION_SERVICE_"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()

