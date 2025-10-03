"""Rendering utilities for notification templates."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from .schemas import Channel, Notification


class TemplateRenderer:
    """Render channel specific templates based on alert type."""

    def __init__(self, template_dir: Path | None = None) -> None:
        base_path = template_dir or Path(__file__).parent / "templates"
        self._environment = Environment(
            loader=FileSystemLoader(str(base_path)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, channel: Channel, notification: Notification) -> str:
        """Return the rendered template for the given channel and alert type."""

        alert_type = notification.metadata.get("type", "default")
        search_paths = [
            f"{channel.value}/{alert_type}.j2",
            f"{channel.value}/default.j2",
            f"default/{alert_type}.j2",
            "default/default.j2",
        ]
        context = {
            "notification": notification,
            "alert_type": alert_type,
            "metadata": self._metadata_without_type(notification.metadata),
        }

        for template_name in search_paths:
            try:
                template = self._environment.get_template(template_name)
            except TemplateNotFound:
                continue
            return template.render(context).strip()

        return f"[{notification.severity.upper()}] {notification.title} - {notification.message}"

    @staticmethod
    def _metadata_without_type(metadata: Dict[str, str]) -> Dict[str, str]:
        """Return metadata without the internal type key to avoid duplication."""

        return {key: value for key, value in metadata.items() if key != "type"}
