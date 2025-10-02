"""Pytest fixtures configuring provider sandbox and live modes."""
from __future__ import annotations

import os
import sys
from collections.abc import Generator
from pathlib import Path

import pytest
import respx


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


_SANDBOX_ENV = "PROVIDERS_SANDBOX_MODE"
_DEFAULT_MODE = "sandbox"


def _sandbox_mode() -> str:
    return os.environ.get(_SANDBOX_ENV, _DEFAULT_MODE).strip().lower()


@pytest.fixture(scope="session")
def sandbox_mode() -> str:
    """Return the configured provider test mode.

    The default mode uses mocked HTTP responses. Setting
    ``PROVIDERS_SANDBOX_MODE=official`` runs the tests against the real
    exchanges instead. Individual tests may still skip themselves if the
    official dependencies are unavailable in the current environment.
    """

    return _sandbox_mode()


@pytest.fixture
def sandbox_respx(sandbox_mode: str) -> Generator[respx.MockRouter | None, None, None]:
    """Provide a respx router when running in sandbox mode."""

    if sandbox_mode != _DEFAULT_MODE:
        yield None
        return
    with respx.mock(assert_all_called=True) as mock:
        yield mock
