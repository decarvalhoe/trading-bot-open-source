#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${USE_NATIVE:-0}" == "1" ]]; then
    "${SCRIPT_DIR}/native_down.sh"
    exit 0
fi

docker compose down -v
echo "-> dev down."
