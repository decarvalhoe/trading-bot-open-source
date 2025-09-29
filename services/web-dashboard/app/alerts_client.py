"""Client utilities for interacting with the alerting engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import httpx


class AlertsEngineError(RuntimeError):
    """Raised when the alert engine returns an error response."""

    def __init__(self, status_code: int, message: str | None = None):
        self.status_code = status_code
        self.message = message or "Alert engine request failed"
        super().__init__(self.message)


@dataclass
class AlertsEngineClient:
    """Simple wrapper around the alert engine HTTP API."""

    base_url: str
    timeout: float = 5.0
    transport: httpx.BaseTransport | None = None

    def __post_init__(self) -> None:
        self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout, transport=self.transport)

    def close(self) -> None:
        self._client.close()

    def create_alert(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        response = self._client.post("/alerts", json=dict(payload))
        return self._parse_response(response)

    def update_alert(self, alert_id: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        response = self._client.put(f"/alerts/{alert_id}", json=dict(payload))
        return self._parse_response(response)

    def delete_alert(self, alert_id: str) -> None:
        response = self._client.delete(f"/alerts/{alert_id}")
        if response.status_code >= 400:
            raise AlertsEngineError(response.status_code, self._extract_message(response))

    @staticmethod
    def _parse_response(response: httpx.Response) -> Mapping[str, Any]:
        if response.status_code >= 400:
            raise AlertsEngineError(response.status_code, AlertsEngineClient._extract_message(response))
        if not response.content:
            return {}
        return response.json()

    @staticmethod
    def _extract_message(response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:  # pragma: no cover - defensive guard for non-json errors
            return response.text or ""
        return (
            data.get("detail")
            or data.get("message")
            or data.get("error")
            or response.text
            or ""
        )


__all__ = ["AlertsEngineClient", "AlertsEngineError"]
