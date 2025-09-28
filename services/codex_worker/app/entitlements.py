"""OpenFeature based entitlement checks for Codex commands."""

from __future__ import annotations

from openfeature import api
from openfeature.evaluation_context import EvaluationContext


class EntitlementChecker:
    """Wrapper around OpenFeature for evaluating entitlements."""

    def __init__(self, environment: str) -> None:
        self._client = api.get_client(environment)

    def is_allowed(self, capability: str, user: str, repository: str) -> bool:
        context = EvaluationContext(
            targeting_key=user,
            attributes={"repository": repository, "capability": capability},
        )
        return self._client.get_boolean_value(capability, False, context)
