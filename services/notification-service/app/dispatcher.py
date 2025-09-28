"""Notification dispatcher implementations."""

from __future__ import annotations

import asyncio
import json
import logging
from email.message import EmailMessage

import httpx

from .config import Settings
from .schemas import Channel, DeliveryTarget, Notification, NotificationRequest, NotificationResponse

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """Dispatch notifications to multiple channels."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def dispatch(self, request: NotificationRequest) -> NotificationResponse:
        """Send the notification to the configured channel."""

        target = request.target
        notification = request.notification

        try:
            if target.channel == Channel.webhook:
                detail = await self._send_webhook(target, notification)
            elif target.channel == Channel.slack:
                detail = await self._send_slack(target, notification)
            elif target.channel == Channel.email:
                detail = await self._send_email(target, notification)
            else:
                raise ValueError(f"Unsupported channel: {target.channel}")
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Delivery failed for channel %s", target.channel.value)
            return NotificationResponse(
                delivered=False,
                channel=target.channel,
                detail=str(exc),
                target=target.identifier(),
            )

        return NotificationResponse(
            delivered=True,
            channel=target.channel,
            detail=detail,
            target=target.identifier(),
        )

    async def _send_webhook(self, target: DeliveryTarget, notification: Notification) -> str:
        if not target.webhook_url:
            raise ValueError("webhook_url must be provided for webhook channel")

        payload = {
            "title": notification.title,
            "message": notification.message,
            "severity": notification.severity,
            "metadata": notification.metadata,
            "created_at": notification.created_at.isoformat(),
        }

        if self._settings.dry_run:
            logger.info("[dry-run] Would post notification to %s", target.webhook_url)
            logger.debug("Payload: %s", json.dumps(payload))
            return "Dry-run: webhook call skipped"

        async with httpx.AsyncClient(timeout=self._settings.http_timeout) as client:
            response = await client.post(target.webhook_url, json=payload)
            response.raise_for_status()
        return f"Webhook delivered with status {response.status_code}"

    async def _send_slack(self, target: DeliveryTarget, notification: Notification) -> str:
        webhook_url = target.webhook_url or self._settings.slack_default_webhook
        if not webhook_url:
            raise ValueError("Slack webhook URL is required")

        payload = {
            "text": f"*{notification.title}*\n{notification.message}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{notification.title}*\n{notification.message}",
                    },
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Severity: `{notification.severity}`",
                        }
                    ],
                },
            ],
        }

        if self._settings.dry_run:
            logger.info("[dry-run] Would post Slack message to %s", webhook_url)
            logger.debug("Payload: %s", json.dumps(payload))
            return "Dry-run: Slack call skipped"

        async with httpx.AsyncClient(timeout=self._settings.http_timeout) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
        return f"Slack webhook delivered with status {response.status_code}"

    async def _send_email(self, target: DeliveryTarget, notification: Notification) -> str:
        if not target.email_to:
            raise ValueError("email_to must be provided for email channel")
        sender = self._settings.smtp_sender or "alerts@example.com"

        message = EmailMessage()
        message["From"] = sender
        message["To"] = target.email_to
        message["Subject"] = f"[{notification.severity.upper()}] {notification.title}"
        body_lines = [notification.message]
        if notification.metadata:
            body_lines.append("\nMéta-données:")
            body_lines.extend(f"- {key}: {value}" for key, value in notification.metadata.items())
        message.set_content("\n".join(body_lines))

        if self._settings.dry_run:
            logger.info("[dry-run] Would send email to %s via %s:%s", target.email_to, self._settings.smtp_host, self._settings.smtp_port)
            logger.debug("Payload: %s", message.as_string())
            return "Dry-run: email send skipped"

        await asyncio.to_thread(
            self._send_email_sync,
            message,
        )
        return "Email accepted for delivery"

    def _send_email_sync(self, message: EmailMessage) -> None:
        """Blocking email sender extracted to ease testing."""

        import smtplib

        with smtplib.SMTP(self._settings.smtp_host, self._settings.smtp_port) as smtp:
            smtp.send_message(message)

