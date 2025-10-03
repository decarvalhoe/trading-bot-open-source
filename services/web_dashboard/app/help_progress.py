"""In-memory tracker for learning activity inside the help center."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Deque, Dict, Set


@dataclass(slots=True)
class LearningResourceVisit:
    """Represents a resource recently consulted by the user."""

    slug: str
    title: str
    resource_type: str
    viewed_at: datetime

    def to_payload(self) -> dict[str, object]:
        return {
            "slug": self.slug,
            "title": self.title,
            "resource_type": self.resource_type,
            "viewed_at": self.viewed_at.isoformat(timespec="seconds"),
        }


@dataclass(slots=True)
class LearningProgress:
    """Aggregated progress metrics for rendering in the UI."""

    user_id: str
    completion_rate: int
    completed_resources: int
    total_resources: int
    recent_resources: list[LearningResourceVisit]

    def to_payload(self) -> dict[str, object]:
        return {
            "user_id": self.user_id,
            "completion_rate": self.completion_rate,
            "completed_resources": self.completed_resources,
            "total_resources": self.total_resources,
            "recent_resources": [visit.to_payload() for visit in self.recent_resources],
        }


class LearningTracker:
    """Minimal tracker storing learning activity per user in memory."""

    def __init__(self, max_recent: int = 5):
        self._max_recent = max_recent
        self._recent: Dict[str, Deque[LearningResourceVisit]] = {}
        self._visited: Dict[str, Set[str]] = {}

    def _ensure_user(self, user_id: str) -> Deque[LearningResourceVisit]:
        if user_id not in self._recent:
            now = datetime.now(UTC)
            seed_history = deque(maxlen=self._max_recent)
            seed_history.append(
                LearningResourceVisit(
                    slug="guide-onboarding",
                    title="Parcours d'onboarding du tableau de bord",
                    resource_type="guide",
                    viewed_at=now - timedelta(days=2, hours=5),
                )
            )
            seed_history.append(
                LearningResourceVisit(
                    slug="faq-api-access",
                    title="Comment connecter mes clés API broker ?",
                    resource_type="faq",
                    viewed_at=now - timedelta(days=1, hours=3),
                )
            )
            self._recent[user_id] = seed_history
            self._visited[user_id] = {visit.slug for visit in seed_history}
        return self._recent[user_id]

    def record_visit(self, user_id: str, slug: str, title: str, resource_type: str) -> None:
        history = self._ensure_user(user_id)
        visited = self._visited.setdefault(user_id, set())

        visited.add(slug)
        history.appendleft(
            LearningResourceVisit(
                slug=slug,
                title=title,
                resource_type=resource_type,
                viewed_at=datetime.now(UTC),
            )
        )

    def get_progress(self, user_id: str, total_resources: int) -> LearningProgress:
        history = list(self._ensure_user(user_id))
        visited = self._visited.setdefault(user_id, set())
        completed = len(visited)
        completion_rate = 0
        if total_resources > 0:
            completion_rate = round((completed / total_resources) * 100)
            if completion_rate > 100:
                completion_rate = 100
        return LearningProgress(
            user_id=user_id,
            completion_rate=completion_rate,
            completed_resources=completed,
            total_resources=total_resources,
            recent_resources=history[: self._max_recent],
        )


_tracker = LearningTracker()


def record_learning_activity(user_id: str, slug: str, title: str, resource_type: str) -> None:
    """Record that a user has consulted a resource."""

    if not user_id or not slug:
        return
    _tracker.record_visit(user_id=user_id, slug=slug, title=title, resource_type=resource_type)


def get_learning_progress(user_id: str, total_resources: int) -> LearningProgress:
    """Return the aggregated learning progress for the given user."""

    return _tracker.get_progress(user_id=user_id, total_resources=total_resources)


__all__ = [
    "LearningProgress",
    "LearningResourceVisit",
    "get_learning_progress",
    "record_learning_activity",
]
