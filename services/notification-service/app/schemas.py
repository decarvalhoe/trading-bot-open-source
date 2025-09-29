"""Pydantic models for the notification service."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, EmailStr, Field


class Channel(str, Enum):
    """Supported delivery channels."""

    webhook = "webhook"
    custom_webhook = "custom_webhook"
    email = "email"
    slack = "slack"
    telegram = "telegram"
    sms = "sms"


class Notification(BaseModel):
    """Core payload describing a critical event."""

    title: str = Field(..., description="Short subject of the message")
    message: str = Field(..., description="Detailed message body")
    severity: str = Field("info", description="info|warning|critical")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional context")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DeliveryTarget(BaseModel):
    """Describe the routing instructions for a notification."""

    channel: Channel
    webhook_url: Optional[str] = Field(None, description="HTTP endpoint for webhook or Slack")
    email_to: Optional[EmailStr] = Field(None, description="Destination address for email delivery")
    telegram_chat_id: Optional[str] = Field(
        None, description="Telegram chat identifier for bot deliveries"
    )
    telegram_bot_token: Optional[str] = Field(
        None, description="Explicit Telegram bot token overriding service defaults", repr=False
    )
    phone_number: Optional[str] = Field(
        None, description="Destination phone number for SMS delivery"
    )

    def identifier(self) -> str:
        """Return a human readable destination id."""

        if self.channel == Channel.email and self.email_to:
            return self.email_to
        if self.channel == Channel.telegram and self.telegram_chat_id:
            return self.telegram_chat_id
        if self.channel == Channel.sms and self.phone_number:
            return self.phone_number
        if self.webhook_url:
            return self.webhook_url
        return self.channel.value


class NotificationRequest(BaseModel):
    """Request payload accepted by the API."""

    notification: Notification
    target: DeliveryTarget


class NotificationResponse(BaseModel):
    """Response returned by the API after attempting delivery."""

    delivered: bool
    channel: Channel
    detail: str
    target: str

