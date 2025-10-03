#!/usr/bin/env bash
set -euo pipefail
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install pydantic fastapi httpx python-dotenv
echo "source .venv/bin/activate" > .envrc || true

