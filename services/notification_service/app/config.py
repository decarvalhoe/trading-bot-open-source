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
    telegram_bot_token: str = Field(
        "",
        description="Default Telegram bot token used when not provided by the delivery target",
        repr=False,
    )
    telegram_default_chat_id: str = Field(
        "",
        description="Fallback Telegram chat identifier for notifications",
    )
    telegram_api_base: str = Field(
        "https://api.telegram.org",
        description="Base URL for Telegram Bot API",
    )
    twilio_account_sid: str = Field(
        "",
        description="Twilio account SID used for SMS notifications",
        repr=False,
    )
    twilio_auth_token: str = Field(
        "",
        description="Twilio auth token used for SMS notifications",
        repr=False,
    )
    twilio_from_number: str = Field(
        "",
        description="Originating phone number configured in Twilio",
    )
    twilio_api_base: str = Field(
        "https://api.twilio.com",
        description="Base URL for the Twilio REST API",
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

