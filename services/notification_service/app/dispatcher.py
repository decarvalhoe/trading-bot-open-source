"""Notification dispatcher implementations."""

from __future__ import annotations

import asyncio
import json
import logging
from email.message import EmailMessage

import httpx

from .config import Settings
from .rendering import TemplateRenderer
from .schemas import Channel, DeliveryTarget, Notification, NotificationRequest, NotificationResponse

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """Dispatch notifications to multiple channels."""

    def __init__(self, settings: Settings, renderer: TemplateRenderer | None = None) -> None:
        self._settings = settings
        self._renderer = renderer or TemplateRenderer()

    async def dispatch(self, request: NotificationRequest) -> NotificationResponse:
        """Send the notification to the configured channel."""

        target = request.target
        notification = request.notification

        try:
            if target.channel in {Channel.webhook, Channel.custom_webhook}:
                detail = await self._send_webhook(target, notification)
            elif target.channel == Channel.slack:
                detail = await self._send_slack(target, notification)
            elif target.channel == Channel.email:
                detail = await self._send_email(target, notification)
            elif target.channel == Channel.telegram:
                detail = await self._send_telegram(target, notification)
            elif target.channel == Channel.sms:
                detail = await self._send_sms(target, notification)
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
        rendered_message = self._renderer.render(target.channel, notification)

        if not target.webhook_url:
            raise ValueError("webhook_url must be provided for webhook channel")

        payload = {
            "title": notification.title,
            "message": notification.message,
            "rendered_message": rendered_message,
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
        rendered_message = self._renderer.render(Channel.slack, notification)

        webhook_url = target.webhook_url or self._settings.slack_default_webhook
        if not webhook_url:
            raise ValueError("Slack webhook URL is required")

        payload = {
            "text": rendered_message,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": rendered_message,
                    },
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Severity: `{notification.severity}`",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"Type: `{notification.metadata.get('type', 'default')}`",
                        },
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
        rendered_message = self._renderer.render(Channel.email, notification)

        if not target.email_to:
            raise ValueError("email_to must be provided for email channel")
        sender = self._settings.smtp_sender or "alerts@example.com"

        message = EmailMessage()
        message["From"] = sender
        message["To"] = target.email_to
        message["Subject"] = f"[{notification.severity.upper()}] {notification.title}"
        message.set_content(rendered_message)

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

    async def _send_telegram(self, target: DeliveryTarget, notification: Notification) -> str:
        rendered_message = self._renderer.render(Channel.telegram, notification)

        token = target.telegram_bot_token or self._settings.telegram_bot_token
        chat_id = target.telegram_chat_id or self._settings.telegram_default_chat_id
        if not token:
            raise ValueError("Telegram bot token is required")
        if not chat_id:
            raise ValueError("Telegram chat id is required")

        api_base = self._settings.telegram_api_base.rstrip("/")
        url = f"{api_base}/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": rendered_message,
        }

        if self._settings.dry_run:
            logger.info("[dry-run] Would send Telegram message to chat %s", chat_id)
            logger.debug("Payload: %s", json.dumps(payload))
            return "Dry-run: Telegram call skipped"

        async with httpx.AsyncClient(timeout=self._settings.http_timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
        if not data.get("ok", True):
            raise RuntimeError(f"Telegram API error: {data.get('description', 'unknown error')}")
        return f"Telegram message sent to chat {chat_id}"

    async def _send_sms(self, target: DeliveryTarget, notification: Notification) -> str:
        rendered_message = self._renderer.render(Channel.sms, notification)

        to_number = target.phone_number
        if not to_number:
            raise ValueError("phone_number must be provided for sms channel")

        account_sid = self._settings.twilio_account_sid
        auth_token = self._settings.twilio_auth_token
        from_number = self._settings.twilio_from_number
        if not all([account_sid, auth_token, from_number]):
            raise ValueError("Twilio credentials and from number must be configured")

        api_base = self._settings.twilio_api_base.rstrip("/")
        url = f"{api_base}/2010-04-01/Accounts/{account_sid}/Messages.json"
        payload = {
            "To": to_number,
            "From": from_number,
            "Body": rendered_message,
        }

        if self._settings.dry_run:
            logger.info("[dry-run] Would send SMS to %s", to_number)
            logger.debug("Payload: %s", json.dumps(payload))
            return "Dry-run: SMS call skipped"

        async with httpx.AsyncClient(timeout=self._settings.http_timeout) as client:
            response = await client.post(url, data=payload, auth=(account_sid, auth_token))
            response.raise_for_status()
            data = response.json()

        sid = data.get("sid") or data.get("message_sid")
        if not sid:
            raise RuntimeError("SMS provider did not return a message SID")
        return f"SMS message queued with sid {sid}"

