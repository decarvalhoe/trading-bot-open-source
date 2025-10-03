#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DATA_ROOT="${PROJECT_ROOT}/data/native"
PGDATA="${DATA_ROOT}/postgres"
REDIS_DATA="${DATA_ROOT}/redis"
REDIS_PID="${REDIS_DATA}/redis.pid"

if command -v pg_ctl >/dev/null 2>&1 && [[ -d "${PGDATA}" ]]; then
    if pg_ctl -D "${PGDATA}" status >/dev/null 2>&1; then
        echo "-> stopping PostgreSQL"
        pg_ctl -D "${PGDATA}" stop -m fast >/dev/null
    fi
fi

if command -v redis-cli >/dev/null 2>&1; then
    if redis-cli -p 6379 ping >/dev/null 2>&1; then
        echo "-> stopping Redis"
        redis-cli -p 6379 shutdown >/dev/null || true
    fi
fi

if [[ -f "${REDIS_PID}" ]]; then
    rm -f "${REDIS_PID}"
fi

echo "-> native services down"
