#!/usr/bin/env bash
set -euo pipefail

RUN_MIGRATIONS="${RUN_MIGRATIONS:-1}"

if [[ "${RUN_MIGRATIONS}" != "1" ]]; then
  exit 0
fi

if ! command -v alembic >/dev/null 2>&1; then
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

ENVIRONMENT="${ENVIRONMENT:-dev}"

DEFAULT_DB_URL="postgresql+psycopg2://trading:trading@localhost:5432/trading"

DB_URL="${ALEMBIC_DATABASE_URL:-${DATABASE_URL:-${POSTGRES_DSN:-${DEFAULT_DB_URL}}}}"

export ALEMBIC_DATABASE_URL="${DB_URL}"

ALEMBIC_CONFIG_PATH="${ALEMBIC_CONFIG:-infra/migrations/alembic.ini}"

echo "Applying database migrations with Alembic using ${ALEMBIC_DATABASE_URL}"
alembic -c "${ALEMBIC_CONFIG_PATH}" upgrade head
