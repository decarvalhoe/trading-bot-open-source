#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEMPLATE_PATH="${ROOT_DIR}/docker-compose.codespaces.yml"
OUTPUT_PATH="${ROOT_DIR}/docker-compose.override.yml"

if [[ ! -f "${TEMPLATE_PATH}" ]]; then
  echo "Unable to find template ${TEMPLATE_PATH}" >&2
  exit 1
fi

CODESPACES_PORT_DOMAIN="${GITHUB_CODESPACES_PORT_DOMAIN:-app.github.dev}"
AUTH_PORT="${AUTH_SERVICE_EXTERNAL_PORT:-8811}"
FRONT_PORT="${WEB_DASHBOARD_EXTERNAL_PORT:-8022}"

if [[ -n "${CODESPACE_NAME:-}" ]]; then
  FRONT_DOMAIN="${CODESPACE_NAME}-${FRONT_PORT}.${CODESPACES_PORT_DOMAIN}"
  AUTH_DOMAIN="${CODESPACE_NAME}-${AUTH_PORT}.${CODESPACES_PORT_DOMAIN}"
else
  FRONT_DOMAIN="localhost:${FRONT_PORT}"
  AUTH_DOMAIN="localhost:${AUTH_PORT}"
fi

if [[ "${FRONT_DOMAIN}" == localhost:* ]]; then
  FRONT_ORIGIN="http://${FRONT_DOMAIN}"
else
  FRONT_ORIGIN="https://${FRONT_DOMAIN}"
fi

if [[ "${AUTH_DOMAIN}" == localhost:* ]]; then
  AUTH_ORIGIN="http://${AUTH_DOMAIN}"
else
  AUTH_ORIGIN="https://${AUTH_DOMAIN}"
fi

WILDCARD_ORIGIN="https://*.${CODESPACES_PORT_DOMAIN}"

export EXISTING_AUTH_ALLOWED="${AUTH_SERVICE_ALLOWED_ORIGINS:-}"
export CODESPACES_DEFAULT_ALLOWED="${FRONT_ORIGIN},${AUTH_ORIGIN},${WILDCARD_ORIGIN}"

COMPUTED_ALLOWED=$(python - <<'PY'
import os
origins = []
for chunk in (os.environ.get("EXISTING_AUTH_ALLOWED", ""), os.environ.get("CODESPACES_DEFAULT_ALLOWED", "")):
    if not chunk:
        continue
    for value in chunk.split(','):
        value = value.strip()
        if value and value not in origins:
            origins.append(value)
print(','.join(origins))
PY
)

AUTH_COOKIE_SECURE="false"
if [[ -n "${CODESPACE_NAME:-}" ]]; then
  AUTH_COOKIE_SECURE="true"
fi

AUTH_COOKIE_DOMAIN=""
if [[ -n "${CODESPACE_NAME:-}" ]]; then
  AUTH_COOKIE_DOMAIN="${FRONT_DOMAIN}"
fi

python - "${TEMPLATE_PATH}" "${OUTPUT_PATH}" "${AUTH_PORT}" "${COMPUTED_ALLOWED}" "${FRONT_PORT}" "${AUTH_ORIGIN}" "${AUTH_COOKIE_SECURE}" "${AUTH_COOKIE_DOMAIN}" <<'PY'
import pathlib
import sys

template_path = pathlib.Path(sys.argv[1])
output_path = pathlib.Path(sys.argv[2])
values = {
    "{{AUTH_SERVICE_PORT}}": sys.argv[3],
    "{{AUTH_SERVICE_ALLOWED_ORIGINS}}": sys.argv[4],
    "{{WEB_DASHBOARD_PORT}}": sys.argv[5],
    "{{WEB_DASHBOARD_AUTH_SERVICE_URL}}": sys.argv[6],
    "{{WEB_DASHBOARD_AUTH_COOKIE_SECURE}}": sys.argv[7],
    "{{WEB_DASHBOARD_AUTH_COOKIE_DOMAIN}}": sys.argv[8],
}
content = template_path.read_text()
for token, value in values.items():
    content = content.replace(token, value)
output_path.write_text(content)
PY

cat <<EOM
Generated ${OUTPUT_PATH} with the following settings:
  Frontend: ${FRONT_ORIGIN}
  Auth service: ${AUTH_ORIGIN}
  Allowed origins: ${COMPUTED_ALLOWED}

You can now run 'make demo-up' to start the demo stack.
EOM
