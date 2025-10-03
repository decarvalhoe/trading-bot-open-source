#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}" >/dev/null 2>&1

ENCRYPTED_ENV_FILE="${ENCRYPTED_ENV_FILE:-.env.enc}"
TEMP_ENV_FILE=""

if [[ -f "${ENCRYPTED_ENV_FILE}" ]]; then
    echo "-> decrypting ${ENCRYPTED_ENV_FILE}"
    TEMP_ENV_FILE="$(mktemp)"
    python -m scripts.dev.env_crypto decrypt --input "${ENCRYPTED_ENV_FILE}" --output "${TEMP_ENV_FILE}"
    set -a
    # shellcheck source=/dev/null
    source "${TEMP_ENV_FILE}"
    set +a
    cleanup() {
        if [[ -f "${TEMP_ENV_FILE}" ]]; then
            rm -f "${TEMP_ENV_FILE}"
        fi
    }
    trap cleanup EXIT
fi

if [[ "${USE_NATIVE:-0}" == "1" ]]; then
    "${SCRIPT_DIR}/native_up.sh"
    echo "-> native dependencies up. start services manually as needed."
    exit 0
fi

docker compose up -d --build
echo "-> dev up. config_service: http://localhost:8000"
