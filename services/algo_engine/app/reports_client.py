"""Client for publishing backtest results to the reports service."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Mapping

import httpx

logger = logging.getLogger(__name__)


class ReportsPublisher:
    """Simple HTTP client pushing analytics to the reports service."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        env_base_url = os.getenv("ALGO_ENGINE_REPORTS_BASE_URL", "http://reports:8000")
        env_timeout = os.getenv("ALGO_ENGINE_REPORTS_TIMEOUT", "5.0")

        self._base_url = (base_url or env_base_url).rstrip("/") or "http://reports:8000"
        try:
            timeout_value = timeout if timeout is not None else float(env_timeout)
        except ValueError as exc:  # pragma: no cover - defensive validation
            raise ValueError("ALGO_ENGINE_REPORTS_TIMEOUT must be numeric") from exc
        self._timeout = timeout_value
        self._client = client

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(base_url=self._base_url, timeout=self._timeout)
        return self._client

    def publish_backtest(self, payload: Mapping[str, Any]) -> None:
        """POST a backtest summary to the reports service."""

        try:
            client = self._get_client()
            response = client.post("/reports/backtests", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            text = exc.response.text
            try:
                body = exc.response.json()
                detail = body.get("detail") if isinstance(body, Mapping) else None
                if detail:
                    text = json.dumps(body)
            except ValueError:
                pass
            logger.warning(
                "reports-service rejected backtest payload with status %s: %s",
                exc.response.status_code,
                text,
            )
        except httpx.HTTPError as exc:
            logger.warning("failed to publish backtest summary to reports-service: %s", exc)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


__all__ = ["ReportsPublisher"]
