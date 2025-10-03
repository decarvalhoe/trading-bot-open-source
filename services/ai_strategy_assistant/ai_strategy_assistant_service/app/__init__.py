"""FastAPI application for the AI strategy assistant."""

from services import _bootstrap  # noqa: F401

from .main import app

__all__ = ["app"]
