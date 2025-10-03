from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

BASE_DIR = Path(__file__).resolve().parent
LOCALES_DIR = BASE_DIR / "locales"
DEFAULT_LANGUAGE = "fr"
AVAILABLE_LANGUAGES = ("fr", "en")
LANG_COOKIE_NAME = "dashboard_lang"


@lru_cache(maxsize=len(AVAILABLE_LANGUAGES) + 2)
def _load_catalog(language: str) -> Dict[str, str]:
    path = LOCALES_DIR / f"{language}.json"
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items()}


@lru_cache(maxsize=len(AVAILABLE_LANGUAGES) + 2)
def get_catalog(language: str) -> Dict[str, str]:
    language = language if language in AVAILABLE_LANGUAGES else DEFAULT_LANGUAGE
    base_catalog = _load_catalog(DEFAULT_LANGUAGE)
    if language == DEFAULT_LANGUAGE:
        return base_catalog
    derived = _load_catalog(language)
    return {**base_catalog, **derived}


def _parse_accept_language(header_value: str | None) -> str | None:
    if not header_value:
        return None
    parts = [part.strip() for part in header_value.split(",") if part.strip()]
    for part in parts:
        code = part.split(";")[0].strip()
        if not code:
            continue
        normalized = code.lower().split("-")[0]
        if normalized in AVAILABLE_LANGUAGES:
            return normalized
    return None


def resolve_language(request: Request) -> str:
    query_param = request.query_params.get("lang")
    if query_param and query_param in AVAILABLE_LANGUAGES:
        return query_param
    cookie_value = request.cookies.get(LANG_COOKIE_NAME)
    if cookie_value and cookie_value in AVAILABLE_LANGUAGES:
        return cookie_value
    header_language = _parse_accept_language(request.headers.get("accept-language"))
    if header_language:
        return header_language
    return DEFAULT_LANGUAGE


def build_translator(language: str) -> Callable[[str], str]:
    catalog = get_catalog(language)

    def translate(message: str, **kwargs: object) -> str:
        text = catalog.get(message, message)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, ValueError):
                pass
        return text

    return translate


class LocalizationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        language = resolve_language(request)
        translator = build_translator(language)
        request.state.language = language
        request.state.translator = translator
        request.state.translations = get_catalog(language)
        response = await call_next(request)
        response.headers.setdefault("Content-Language", language)
        if request.query_params.get("lang"):
            response.set_cookie(
                LANG_COOKIE_NAME,
                language,
                path="/",
                max_age=60 * 60 * 24 * 365,
                httponly=False,
                secure=False,
            )
        return response


def template_base_context(request: Request) -> Dict[str, object]:
    translator = getattr(request.state, "translator", None)
    if not callable(translator):
        translator = build_translator(DEFAULT_LANGUAGE)
    language = getattr(request.state, "language", DEFAULT_LANGUAGE)
    translations = getattr(request.state, "translations", get_catalog(language))
    return {
        "_": translator,
        "current_language": language,
        "available_languages": AVAILABLE_LANGUAGES,
        "language_labels": {
            "fr": translator("Français"),
            "en": translator("Anglais"),
        },
        "i18n_bundle": {
            "language": language,
            "translations": {lang: get_catalog(lang) for lang in AVAILABLE_LANGUAGES},
            "languages": list(AVAILABLE_LANGUAGES),
        },
        "translations": translations,
    }
