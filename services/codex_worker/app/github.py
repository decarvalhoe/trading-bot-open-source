"""Client for interacting with the GitHub REST API."""

from __future__ import annotations

from typing import Any

import httpx


class GitHubClient:
    """Minimal GitHub REST client supporting Checks and PR interactions."""

    def __init__(
        self,
        token: str,
        base_url: str = "https://api.github.com",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "codex-worker",
            },
        )
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def create_check_run(self, repository: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post(f"/repos/{repository}/check-runs", json=payload)
        response.raise_for_status()
        return response.json()

    async def update_check_run(
        self, repository: str, check_run_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        response = await self._client.patch(
            f"/repos/{repository}/check-runs/{check_run_id}", json=payload
        )
        response.raise_for_status()
        return response.json()

    async def post_pr_comment(
        self, repository: str, pull_number: int, body: str
    ) -> dict[str, Any]:
        response = await self._client.post(
            f"/repos/{repository}/issues/{pull_number}/comments", json={"body": body}
        )
        response.raise_for_status()
        return response.json()

    async def merge_pull_request(
        self, repository: str, pull_number: int, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        response = await self._client.put(
            f"/repos/{repository}/pulls/{pull_number}/merge", json=payload or {}
        )
        response.raise_for_status()
        return response.json()
