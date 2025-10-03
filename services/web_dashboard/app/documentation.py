"""Helpers for exposing strategy documentation in the dashboard."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Literal

import markdown


REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS_DIR = REPO_ROOT / "docs"
STRATEGY_DOC_PATH = DOCS_DIR / "strategies" / "README.md"
SCHEMA_VERSION_PATH = DOCS_DIR / "strategies" / "VERSION"
TUTORIALS_DIR = DOCS_DIR / "tutorials"
TUTORIALS_INDEX_PATH = TUTORIALS_DIR / "README.md"

DEFAULT_GITHUB_BASE = "https://github.com/decarvalhoe/trading-bot-open-source/blob/main"
GITHUB_BASE_URL = os.getenv("WEB_DASHBOARD_DOCS_GITHUB_BASE", DEFAULT_GITHUB_BASE)
DESIGNER_EMBED_URL = os.getenv("WEB_DASHBOARD_DESIGNER_TUTORIAL_EMBED", "")


@dataclass(slots=True)
class TutorialAsset:
    """Represents a tutorial surfaced alongside the strategy documentation."""

    slug: str
    title: str
    notes_html: str
    embed_kind: Literal["iframe", "video", "html"]
    embed_title: str | None = None
    embed_url: str | None = None
    embed_html: str | None = None
    source_url: str | None = None


@dataclass(slots=True)
class StrategyDocumentation:
    """Bundle of rendered documentation artefacts for the UI."""

    schema_version: str
    body_html: str
    tutorials: list[TutorialAsset]


def _markdown_to_html(text: str) -> str:
    if not text.strip():
        return ""
    return markdown.markdown(
        text,
        extensions=[
            "markdown.extensions.extra",
            "markdown.extensions.sane_lists",
        ],
        output_format="html5",
    )


def _slugify(value: str) -> str:
    cleaned = [
        ch.lower() if ch.isalnum() else "-"
        for ch in value.strip()
    ]
    slug = "".join(cleaned)
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")
    return slug or "section"


def _load_schema_version() -> str:
    if SCHEMA_VERSION_PATH.exists():
        version = SCHEMA_VERSION_PATH.read_text(encoding="utf-8").strip()
        if version:
            return version
    return "non spécifiée"


def _load_strategy_markdown() -> str:
    if STRATEGY_DOC_PATH.exists():
        return STRATEGY_DOC_PATH.read_text(encoding="utf-8")
    return (
        "# Documentation manquante\n\n"
        "Impossible de localiser `docs/strategies/README.md`."
    )


def _iter_tutorial_sections(text: str) -> Iterable[tuple[str, str]]:
    current_title: str | None = None
    current_lines: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            if current_title is not None:
                yield current_title, "\n".join(current_lines).strip()
            current_title = line[3:].strip()
            current_lines = []
            continue
        if current_title is None:
            continue
        current_lines.append(raw_line)

    if current_title is not None:
        yield current_title, "\n".join(current_lines).strip()


def _build_tutorial_asset(title: str, body: str) -> TutorialAsset:
    slug = _slugify(title)
    notes_html = _markdown_to_html(body)
    lowered = title.lower()
    embed_kind: Literal["iframe", "video", "html"] = "html"
    embed_title = None
    embed_url = None
    embed_html = None
    source_url = None

    if "backtest" in lowered and "notebook" in lowered:
        embed_kind = "iframe"
        embed_title = "Notebook backtest-sandbox.ipynb"
        embed_url = (
            "https://nbviewer.org/github/decarvalhoe/trading-bot-open-source/blob/main/"
            "docs/tutorials/backtest-sandbox.ipynb"
        )
        source_url = f"{GITHUB_BASE_URL}/docs/tutorials/backtest-sandbox.ipynb"
    elif "screencast" in lowered:
        if DESIGNER_EMBED_URL:
            embed_kind = "video"
            embed_title = "Screencast Strategy Designer"
            embed_url = DESIGNER_EMBED_URL
        else:
            embed_kind = "html"
            embed_html = (
                "<p class=\"text text--muted\">"
                "Le screencast est hébergé dans la vidéothèque interne. "
                "Suivez le lien de la fiche tutoriel pour y accéder."
                "</p>"
            )
        source_url = f"{GITHUB_BASE_URL}/docs/tutorials/README.md#strategy-designer-screencast"
    elif "dashboard" in lowered and "walkthrough" in lowered:
        embed_kind = "html"
        embed_html = (
            "<p class=\"text text--muted\">"
            "Ce tutoriel fournit un guide pas-à-pas. Consultez les notes pour les instructions complètes."
            "</p>"
        )
        source_url = f"{GITHUB_BASE_URL}/docs/tutorials/README.md#real-time-dashboard-walkthrough"

    return TutorialAsset(
        slug=slug,
        title=title,
        notes_html=notes_html,
        embed_kind=embed_kind,
        embed_title=embed_title,
        embed_url=embed_url,
        embed_html=embed_html,
        source_url=source_url,
    )


def _load_tutorial_assets() -> list[TutorialAsset]:
    if not TUTORIALS_INDEX_PATH.exists():
        return []
    sections = list(_iter_tutorial_sections(TUTORIALS_INDEX_PATH.read_text(encoding="utf-8")))
    return [_build_tutorial_asset(title, body) for title, body in sections]


@lru_cache(maxsize=1)
def load_strategy_documentation() -> StrategyDocumentation:
    """Load and render the strategy documentation bundle once per process."""

    doc_markdown = _load_strategy_markdown()
    schema_html = _markdown_to_html(doc_markdown)
    schema_version = _load_schema_version()
    tutorials = _load_tutorial_assets()
    return StrategyDocumentation(
        schema_version=schema_version,
        body_html=schema_html,
        tutorials=tutorials,
    )


__all__ = [
    "StrategyDocumentation",
    "TutorialAsset",
    "load_strategy_documentation",
]
