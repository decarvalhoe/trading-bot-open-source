#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DATA_ROOT="${PROJECT_ROOT}/data/native"
PGDATA="${DATA_ROOT}/postgres"
REDIS_DATA="${DATA_ROOT}/redis"
PG_LOG="${PGDATA}/server.log"
REDIS_LOG="${REDIS_DATA}/redis.log"
REDIS_PID="${REDIS_DATA}/redis.pid"

mkdir -p "${PGDATA}" "${REDIS_DATA}"

for cmd in pg_ctl pg_isready initdb redis-server redis-cli; do
    if ! command -v "${cmd}" >/dev/null 2>&1; then
        echo "Error: ${cmd} is required but not installed or not on PATH." >&2
        exit 1
    fi
done

if [[ ! -f "${PGDATA}/PG_VERSION" ]]; then
    echo "-> initializing PostgreSQL data directory at ${PGDATA}"
    initdb -D "${PGDATA}" >/dev/null
fi

if ! pg_ctl -D "${PGDATA}" status >/dev/null 2>&1; then
    echo "-> starting PostgreSQL on port 5432"
    pg_ctl -D "${PGDATA}" -l "${PG_LOG}" -o "-p 5432" start >/dev/null
fi

echo "-> waiting for PostgreSQL to become ready"
until pg_isready -q -h localhost -p 5432; do
    sleep 1
done

echo "-> PostgreSQL is ready"

if ! redis-cli -p 6379 ping >/dev/null 2>&1; then
    echo "-> starting Redis on port 6379"
    redis-server --daemonize yes --port 6379 --dir "${REDIS_DATA}" --pidfile "${REDIS_PID}" --logfile "${REDIS_LOG}" >/dev/null
fi

echo "-> waiting for Redis to become ready"
until redis-cli -p 6379 ping >/dev/null 2>&1; do
    sleep 1
done

echo "-> Redis is ready"

echo "-> native services up (PostgreSQL @ 5432, Redis @ 6379)"
