"""Unit tests for the Codex worker."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from openfeature import api
from openfeature.provider.in_memory_provider import InMemoryFlag, InMemoryProvider

from libs.codex import CodexEvent, CodexEventPayload
from services.codex_worker.app.entitlements import EntitlementChecker
from services.codex_worker.app.worker import CodexWorker
from services.codex_worker.app.sandbox import SandboxResult


@pytest.fixture(autouse=True)
def configure_openfeature() -> None:
    flags = {
        "codex.plan": InMemoryFlag(default_variant="on", variants={"on": True}),
        "codex.pr": InMemoryFlag(default_variant="on", variants={"on": True}),
    }
    api.set_provider(InMemoryProvider(flags))
    yield
    api.clear_providers()


def make_github_payload(command: str) -> dict[str, object]:
    return {
        "action": "created",
        "comment": {"body": f"/codex {command}", "user": {"login": "alice"}},
        "issue": {"number": 7, "pull_request": {"head": {"sha": "abc123"}}},
        "repository": {"full_name": "octo/repo"},
    }


@pytest.mark.asyncio
async def test_worker_runs_plan() -> None:
    consumer = AsyncMock()
    github = AsyncMock()
    github.create_check_run.return_value = {"id": 42}
    sandbox = AsyncMock()
    sandbox.run.return_value = SandboxResult(success=True, logs="tests passed", exit_code=0)

    checker = EntitlementChecker("codex")
    worker = CodexWorker(consumer, github, sandbox, checker)

    payload = make_github_payload("plan")
    event = CodexEvent(
        provider="github",
        eventType="issue_comment",
        payload=CodexEventPayload(
            contentType="application/json",
            body=json.dumps(payload).encode("utf-8"),
        ),
    )

    await worker._handle_event(event)

    github.create_check_run.assert_awaited_once()
    sandbox.run.assert_awaited_once()
    github.update_check_run.assert_awaited_once()
    github.post_pr_comment.assert_awaited()


@pytest.mark.asyncio
async def test_worker_denies_command_without_entitlement() -> None:
    flags = {
        "codex.plan": InMemoryFlag(default_variant="off", variants={"off": False}),
    }
    api.set_provider(InMemoryProvider(flags))

    consumer = AsyncMock()
    github = AsyncMock()
    sandbox = AsyncMock()
    checker = EntitlementChecker("codex")
    worker = CodexWorker(consumer, github, sandbox, checker)

    payload = make_github_payload("plan")
    event = CodexEvent(
        provider="github",
        eventType="issue_comment",
        payload=CodexEventPayload(
            contentType="application/json",
            body=json.dumps(payload).encode("utf-8"),
        ),
    )

    await worker._handle_event(event)

    github.post_pr_comment.assert_awaited_once()
    sandbox.run.assert_not_called()
    github.create_check_run.assert_not_called()
