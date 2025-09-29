import asyncio
import sys
from pathlib import Path

import pytest
import httpx

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from app.config import Settings
from app.dispatcher import NotificationDispatcher
from app.schemas import Channel, DeliveryTarget, Notification, NotificationRequest


def mock_async_client(monkeypatch, expected_url: str, *, status_code: int, json_body: dict | None = None):
    calls: dict[str, object] = {}

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            calls["init_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, data=None, auth=None):
            assert url == expected_url
            calls["url"] = url
            calls["json"] = json
            calls["data"] = data
            calls["auth"] = auth
            return httpx.Response(
                status_code=status_code,
                json=json_body,
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(httpx, "AsyncClient", DummyAsyncClient)
    calls["expected_url"] = expected_url
    return calls


def build_notification() -> Notification:
    return Notification(
        title="System Alert",
        message="Service latency is above threshold",
        severity="critical",
        metadata={"service": "api"},
    )


def test_dispatch_webhook_dry_run() -> None:
    settings = Settings(dry_run=True)
    dispatcher = NotificationDispatcher(settings)
    request = NotificationRequest(
        notification=build_notification(),
        target=DeliveryTarget(channel=Channel.webhook, webhook_url="https://example.com/hook"),
    )

    response = asyncio.run(dispatcher.dispatch(request))

    assert response.delivered is True
    assert response.detail == "Dry-run: webhook call skipped"


def test_dispatch_custom_webhook_uses_same_sender() -> None:
    settings = Settings(dry_run=True)
    dispatcher = NotificationDispatcher(settings)
    request = NotificationRequest(
        notification=build_notification(),
        target=DeliveryTarget(channel=Channel.custom_webhook, webhook_url="https://example.com/custom"),
    )

    response = asyncio.run(dispatcher.dispatch(request))

    assert response.delivered is True
    assert response.detail == "Dry-run: webhook call skipped"


def test_dispatch_slack_success(monkeypatch: pytest.MonkeyPatch) -> None:
    webhook = "https://hooks.slack.com/services/T000/B000/XXX"
    calls = mock_async_client(monkeypatch, webhook, status_code=200, json_body={})

    settings = Settings(dry_run=False, slack_default_webhook=webhook)
    dispatcher = NotificationDispatcher(settings)
    request = NotificationRequest(
        notification=build_notification(),
        target=DeliveryTarget(channel=Channel.slack),
    )

    response = asyncio.run(dispatcher.dispatch(request))

    assert response.delivered is True
    assert "Slack webhook delivered" in response.detail
    assert calls["json"]["text"].startswith("*System Alert*")


def test_dispatch_email_dry_run() -> None:
    settings = Settings(dry_run=True, smtp_sender="alerts@example.com")
    dispatcher = NotificationDispatcher(settings)
    request = NotificationRequest(
        notification=build_notification(),
        target=DeliveryTarget(channel=Channel.email, email_to="ops@example.com"),
    )

    response = asyncio.run(dispatcher.dispatch(request))

    assert response.delivered is True
    assert response.detail == "Dry-run: email send skipped"


def test_dispatch_telegram_success(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "https://api.telegram.org/botTOKEN/sendMessage"
    calls = mock_async_client(
        monkeypatch,
        url,
        status_code=200,
        json_body={"ok": True, "result": {"message_id": 42}},
    )

    settings = Settings(
        dry_run=False,
        telegram_api_base="https://api.telegram.org",
        telegram_bot_token="TOKEN",
    )
    dispatcher = NotificationDispatcher(settings)
    request = NotificationRequest(
        notification=build_notification(),
        target=DeliveryTarget(channel=Channel.telegram, telegram_chat_id="1234"),
    )

    response = asyncio.run(dispatcher.dispatch(request))

    assert response.delivered is True
    assert response.detail == "Telegram message sent to chat 1234"
    assert calls["json"]["chat_id"] == "1234"


def test_dispatch_sms_success(monkeypatch: pytest.MonkeyPatch) -> None:
    api_base = "https://api.twilio.com"
    url = f"{api_base}/2010-04-01/Accounts/ACCT/Messages.json"
    calls = mock_async_client(
        monkeypatch,
        url,
        status_code=201,
        json_body={"sid": "SM123"},
    )

    settings = Settings(
        dry_run=False,
        twilio_api_base=api_base,
        twilio_account_sid="ACCT",
        twilio_auth_token="secret",
        twilio_from_number="+100000000",
    )
    dispatcher = NotificationDispatcher(settings)
    request = NotificationRequest(
        notification=build_notification(),
        target=DeliveryTarget(channel=Channel.sms, phone_number="+33102030405"),
    )

    response = asyncio.run(dispatcher.dispatch(request))

    assert response.delivered is True
    assert response.detail == "SMS message queued with sid SM123"
    assert calls["data"]["To"] == "+33102030405"
