#!/usr/bin/env bash
set -euo pipefail
docker compose up -d --build
echo "-> dev up. config-service: http://localhost:8000"
