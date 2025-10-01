#!/usr/bin/env python3
"""Backward compatible wrapper that delegates to :mod:`bootstrap_demo`."""
from __future__ import annotations

from scripts.dev import bootstrap_demo


def main() -> None:
    """Execute the new bootstrap demo flow."""

    bootstrap_demo.main()


if __name__ == "__main__":
    main()
