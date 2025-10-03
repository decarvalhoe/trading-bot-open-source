"""Asynchronous worker consuming Codex automation events."""

from __future__ import annotations

import logging
from typing import Any

from libs.codex import CodexEvent, EventConsumer

from .entitlements import EntitlementChecker
from .github import GitHubClient
from .sandbox import SandboxResult, SandboxRunner

LOGGER = logging.getLogger("codex.worker")


class CodexWorker:
    """Consume events and orchestrate automation tasks."""

    def __init__(
        self,
        consumer: EventConsumer,
        github: GitHubClient,
        sandbox: SandboxRunner,
        entitlements: EntitlementChecker,
    ) -> None:
        self._consumer = consumer
        self._github = github
        self._sandbox = sandbox
        self._entitlements = entitlements

    async def run_forever(self) -> None:
        """Continuously consume events from the broker."""

        while True:
            event = await self._consumer.get()
            try:
                await self._handle_event(event)
            except Exception as exc:  # pragma: no cover - best effort logging
                LOGGER.exception("Failed to process event %s: %s", event.id, exc)

    async def _handle_event(self, event: CodexEvent) -> None:
        if event.provider == "github":
            await self._handle_github_event(event)
        else:
            LOGGER.info("Ignoring event from provider %s", event.provider)

    async def _handle_github_event(self, event: CodexEvent) -> None:
        try:
            payload = event.body_as_json()
        except ValueError:
            LOGGER.warning("Received non JSON GitHub payload")
            return

        event_type = event.event_type or payload.get("action")
        if event_type != "issue_comment":
            LOGGER.debug("Unsupported GitHub event type: %s", event_type)
            return

        if payload.get("action") != "created":
            LOGGER.debug("Ignoring non creation comment event")
            return

        comment_body = payload.get("comment", {}).get("body", "")
        command = self._parse_command(comment_body)
        if not command:
            return

        repository = payload.get("repository", {}).get("full_name")
        pull_number = payload.get("issue", {}).get("number")
        user = payload.get("comment", {}).get("user", {}).get("login", "")
        if not repository or not pull_number:
            LOGGER.warning("Missing repository context in GitHub event")
            return

        capability = f"codex.{command}"
        if not self._entitlements.is_allowed(capability, user or "anonymous", repository):
            await self._github.post_pr_comment(
                repository,
                pull_number,
                "🚫 Vous n'avez pas les droits nécessaires pour exécuter cette commande.",
            )
            return

        if command == "plan":
            await self._execute_plan(repository, pull_number, payload)
        elif command == "pr":
            await self._execute_pr(repository, pull_number, payload)

    async def _execute_plan(
        self, repository: str, pull_number: int, payload: dict[str, Any]
    ) -> None:
        head_sha = payload.get("issue", {}).get("pull_request", {}).get("head", {}).get("sha")
        if not head_sha:
            LOGGER.warning("Unable to determine head SHA for PR #%s", pull_number)
            return

        check_run = await self._github.create_check_run(
            repository,
            {
                "name": "codex-plan",
                "head_sha": head_sha,
                "status": "in_progress",
            },
        )

        commands = [
            "set -e",
            "mkdir -p /workspace/src",
            "cd /workspace/src",
            f"if [ ! -d {repository.split('/')[-1]} ]; then git clone https://github.com/{repository}.git; fi",
            f"cd {repository.split('/')[-1]}",
            "git fetch origin",
            f"git checkout {head_sha}",
            "pip install -r requirements-dev.txt || true",
            "pytest",
        ]
        result = await self._sandbox.run(repository, commands)
        await self._finalize_check_run(repository, check_run, result)

        summary = "✅ Plan réussi" if result.success else "❌ Plan en erreur"
        body = f"{summary}\n\n```\n{result.logs[-4000:]}\n```"
        await self._github.post_pr_comment(repository, pull_number, body)

    async def _execute_pr(self, repository: str, pull_number: int, payload: dict[str, Any]) -> None:
        await self._github.post_pr_comment(
            repository,
            pull_number,
            "▶️ Déclenchement du workflow PR...",
        )
        await self._github.merge_pull_request(
            repository,
            pull_number,
            payload={"merge_method": "squash"},
        )

    async def _finalize_check_run(
        self, repository: str, check_run: dict[str, Any], result: SandboxResult
    ) -> None:
        check_run_id = check_run.get("id")
        if not isinstance(check_run_id, int):
            LOGGER.warning("Invalid check run identifier returned by GitHub")
            return

        conclusion = "success" if result.success else "failure"
        output = {
            "title": "Codex plan",
            "summary": result.logs[:1024],
            "text": result.logs[:65535],
        }
        await self._github.update_check_run(
            repository,
            check_run_id,
            {
                "status": "completed",
                "conclusion": conclusion,
                "output": output,
            },
        )

    @staticmethod
    def _parse_command(comment: str) -> str | None:
        for line in comment.splitlines():
            line = line.strip()
            if not line.startswith("/codex"):
                continue
            parts = line.split()
            if len(parts) < 2:
                return None
            return parts[1]
        return None
