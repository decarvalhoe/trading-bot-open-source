"""Adapters for sending outbound notifications to third party platforms."""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from .config import Settings

logger = logging.getLogger(__name__)


async def post_discord_embed(settings: Settings, webhook_url: str, embed: dict) -> None:
    """Send a Discord embed message."""

    if not webhook_url:
        logger.info("Skipping Discord notification because webhook URL is missing")
        return
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(webhook_url, json={"embeds": [embed]})
        if response.status_code >= 400:
            logger.warning("Discord webhook failed: %s", response.text)


async def announce_session_start(settings: Settings, session_id: str, overlay_url: str, webhook_url: Optional[str]) -> None:
    """Announce the start of a live session on Discord."""

    if not webhook_url:
        return
    embed = {
        "title": "Live session started",
        "description": f"Overlay is live: {overlay_url}",
        "color": 0x9146FF,
        "fields": [{"name": "Session ID", "value": session_id}],
    }
    await post_discord_embed(settings, webhook_url, embed)
