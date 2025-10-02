"""Helpers for exposing the help & training knowledge base."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, Literal

import markdown


REPO_ROOT = Path(__file__).resolve().parents[3]
HELP_ROOT = REPO_ROOT / "docs" / "help"
CATALOG_PATH = HELP_ROOT / "catalog.json"

HelpArticleType = Literal["faq", "guide", "webinar", "notebook"]


@dataclass(slots=True)
class HelpArticle:
    """Single article rendered for the help center UI."""

    slug: str
    title: str
    summary: str
    resource_type: HelpArticleType
    category: str
    body_html: str
    resource_link: str | None = None
    tags: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, object]:
        return {
            "slug": self.slug,
            "title": self.title,
            "summary": self.summary,
            "resource_type": self.resource_type,
            "category": self.category,
            "body_html": self.body_html,
            "resource_link": self.resource_link,
            "tags": list(self.tags),
        }


@dataclass(slots=True)
class HelpCenterContent:
    """Bundle of articles grouped by resource type."""

    articles: list[HelpArticle]
    sections: dict[HelpArticleType, list[HelpArticle]]

    def get_section(self, resource_type: HelpArticleType) -> list[HelpArticle]:
        return self.sections.get(resource_type, [])

    @property
    def faq(self) -> list[HelpArticle]:
        return self.get_section("faq")

    @property
    def guides(self) -> list[HelpArticle]:
        return self.get_section("guide")

    @property
    def webinars(self) -> list[HelpArticle]:
        return self.get_section("webinar")

    @property
    def notebooks(self) -> list[HelpArticle]:
        return self.get_section("notebook")

    def to_payload(self) -> dict[str, object]:
        return {
            "articles": [article.to_payload() for article in self.articles],
            "sections": {
                section: [article.to_payload() for article in articles]
                for section, articles in self.sections.items()
            },
        }


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


def _load_catalog() -> Iterable[dict[str, object]]:
    if not CATALOG_PATH.exists():
        return []
    try:
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:  # pragma: no cover - defensive guard
        return []
    if not isinstance(catalog, list):
        return []
    return catalog


def _load_article(entry: dict[str, object]) -> HelpArticle | None:
    slug = str(entry.get("slug") or "").strip()
    title = str(entry.get("title") or "").strip()
    summary = str(entry.get("summary") or "").strip()
    resource_type = str(entry.get("resource_type") or "").strip().lower()
    category = str(entry.get("category") or "").strip() or "Ressources"
    body_path = str(entry.get("body_path") or "").strip()
    resource_link = entry.get("resource_link")
    tags_field = entry.get("tags")

    if not slug or not title or not body_path:
        return None
    if resource_type not in {"faq", "guide", "webinar", "notebook"}:
        resource_type = "guide"

    body_file = HELP_ROOT / body_path
    if not body_file.exists():
        body_html = "<p class=\"text text--muted\">Contenu introuvable.</p>"
    else:
        body_html = _markdown_to_html(body_file.read_text(encoding="utf-8"))

    tags: list[str] = []
    if isinstance(tags_field, list):
        tags = [str(tag).strip() for tag in tags_field if str(tag).strip()]

    link_value: str | None = None
    if isinstance(resource_link, str) and resource_link.strip():
        link_value = resource_link.strip()

    return HelpArticle(
        slug=slug,
        title=title,
        summary=summary,
        resource_type=resource_type,  # type: ignore[arg-type]
        category=category,
        body_html=body_html,
        resource_link=link_value,
        tags=tags,
    )


@lru_cache(maxsize=1)
def load_help_center() -> HelpCenterContent:
    """Load and group all help center resources."""

    articles: list[HelpArticle] = []
    sections: Dict[HelpArticleType, list[HelpArticle]] = {
        "faq": [],
        "guide": [],
        "webinar": [],
        "notebook": [],
    }

    for entry in _load_catalog():
        if not isinstance(entry, dict):
            continue
        article = _load_article(entry)
        if article is None:
            continue
        articles.append(article)
        sections[article.resource_type].append(article)

    articles.sort(key=lambda article: article.title.lower())
    for bucket in sections.values():
        bucket.sort(key=lambda article: article.title.lower())

    return HelpCenterContent(articles=articles, sections=sections)


def get_article_by_slug(slug: str) -> HelpArticle | None:
    slug = slug.strip().lower()
    if not slug:
        return None
    content = load_help_center()
    for article in content.articles:
        if article.slug.lower() == slug:
            return article
    return None


__all__ = [
    "HelpArticle",
    "HelpCenterContent",
    "HelpArticleType",
    "get_article_by_slug",
    "load_help_center",
]
