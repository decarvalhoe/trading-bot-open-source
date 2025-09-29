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


class AlertTriggerNotification(BaseModel):
    """Payload received from the alert engine when a rule fires."""

    event_id: int | None = Field(default=None, description="Identifier generated for the stored event")
    trigger_id: int = Field(..., description="Primary key of the trigger in the alert engine store")
    rule_id: int = Field(..., description="Identifier of the rule that fired")
    rule_name: str = Field(..., description="Name of the alerting rule")
    strategy: str = Field(..., description="Strategy or grouping the rule belongs to")
    severity: str = Field(..., description="info|warning|critical severity level")
    symbol: str = Field(..., description="Market symbol used when evaluating the rule")
    triggered_at: datetime = Field(..., description="Timestamp when the rule fired")
    context: Dict[str, object] = Field(default_factory=dict, description="Captured evaluation context")
    notification_channel: str | None = Field(
        default=None, description="Optional downstream channel suggested for delivery"
    )
    notification_target: str | None = Field(
        default=None,
        description="Optional destination identifier (email, webhook…) to pre-fill history",
    )

