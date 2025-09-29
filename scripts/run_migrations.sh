#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

DEFAULT_DB_URL="postgresql+psycopg2://trading:trading@postgres:5432/trading"
DB_URL="${ALEMBIC_DATABASE_URL:-${DATABASE_URL:-${DEFAULT_DB_URL}}}"

export ALEMBIC_DATABASE_URL="${DB_URL}"

ALEMBIC_CONFIG_PATH="${ALEMBIC_CONFIG:-infra/migrations/alembic.ini}"

echo "Applying database migrations with Alembic using ${ALEMBIC_DATABASE_URL}"
alembic -c "${ALEMBIC_CONFIG_PATH}" upgrade head
