"""Command line entrypoint to execute Codex worker logic from CI."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from libs.codex import CodexEvent, CodexEventPayload, MemoryEventBroker

from .config import get_settings
from .entitlements import EntitlementChecker
from .github import GitHubClient
from .sandbox import SandboxRunner
from .worker import CodexWorker


async def run_once(event: CodexEvent) -> None:
    settings = get_settings()
    broker = MemoryEventBroker()
    github = GitHubClient(settings.github_token)
    sandbox = SandboxRunner(settings.sandbox_image, settings.checkout_root)
    entitlements = EntitlementChecker(settings.feature_flag_environment)
    worker = CodexWorker(broker, github, sandbox, entitlements)
    await worker._handle_event(event)
    await github.close()


def load_event(provider: str, event_type: str, path: Path) -> CodexEvent:
    payload = path.read_text(encoding="utf-8")
    return CodexEvent(
        provider=provider,
        eventType=event_type,
        payload=CodexEventPayload(contentType="application/json", body=payload.encode("utf-8")),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute a Codex worker run for a single event")
    parser.add_argument(
        "--provider", default="github", help="Event provider (github|stripe|tradingview)"
    )
    parser.add_argument("--event-type", default="issue_comment", help="Type de l'événement")
    parser.add_argument("--event-path", required=True, help="Chemin vers le payload JSON")
    args = parser.parse_args()

    event = load_event(args.provider, args.event_type, Path(args.event_path))
    asyncio.run(run_once(event))


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
