set -euo pipefail
export NO_PROXY="localhost,127.0.0.1"; export no_proxy="$NO_PROXY"

curl --noproxy "*" -sf http://127.0.0.1:8011/health >/dev/null

email="dev$(date +%Y%m%d%H%M%S)@example.com"
curl --noproxy "*" -sS -X POST http://127.0.0.1:8011/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$email\",\"password\":\"Passw0rd!\"}" >/dev/null

token=$(curl --noproxy "*" -sS -X POST http://127.0.0.1:8011/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$email\",\"password\":\"Passw0rd!\"}" | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl --noproxy "*" -sS -H "Authorization: Bearer $token" http://127.0.0.1:8011/auth/me >/dev/null
echo "E2E DONE ✅"
