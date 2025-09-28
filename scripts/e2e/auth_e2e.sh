set -euo pipefail
export NO_PROXY="localhost,127.0.0.1"; export no_proxy="$NO_PROXY"

curl --noproxy "*" -sf http://127.0.0.1:8011/health >/dev/null
curl --noproxy "*" -sf http://127.0.0.1:8012/health >/dev/null

email="dev$(date +%Y%m%d%H%M%S)@example.com"
password="Passw0rd!"

curl --noproxy "*" -sS -X POST http://127.0.0.1:8011/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$email\",\"password\":\"$password\"}" >/dev/null

token=$(curl --noproxy "*" -sS -X POST http://127.0.0.1:8011/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$email\",\"password\":\"$password\"}" | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl --noproxy "*" -sS -H "Authorization: Bearer $token" http://127.0.0.1:8011/auth/me >/dev/null

user_payload=$(cat <<JSON
{
  "email": "$email",
  "display_name": "Dev User"
}
JSON
)

user_response=$(curl --noproxy "*" -sS -X POST http://127.0.0.1:8012/users/register \
  -H "Content-Type: application/json" \
  -d "$user_payload")
user_id=$(python -c "import sys,json; print(json.load(sys.stdin)['id'])" <<<"$user_response")

user_token=$(python - <<PY
import json
import os
from datetime import datetime, timezone
from jose import jwt
secret = os.getenv('JWT_SECRET', 'dev-secret-change-me')
now = int(datetime.now(timezone.utc).timestamp())
payload = {"sub": str($user_id), "iat": now}
print(jwt.encode(payload, secret, algorithm='HS256'))
PY
)

profile_payload=$(cat <<JSON
{
  "display_name": "Dev Trader",
  "full_name": "Developer Example",
  "locale": "fr_FR",
  "marketing_opt_in": true
}
JSON
)

curl --noproxy "*" -sS -X POST http://127.0.0.1:8012/users/$user_id/activate \
  -H "Authorization: Bearer $user_token" \
  -H "x-customer-id: $user_id" >/dev/null

curl --noproxy "*" -sS -X PATCH http://127.0.0.1:8012/users/$user_id \
  -H "Authorization: Bearer $user_token" \
  -H "x-customer-id: $user_id" \
  -H "Content-Type: application/json" \
  -d "$profile_payload" >/dev/null

preferences_payload='{"preferences":{"theme":"dark","currency":"EUR"}}'

curl --noproxy "*" -sS -X PUT http://127.0.0.1:8012/users/me/preferences \
  -H "Authorization: Bearer $user_token" \
  -H "x-customer-id: $user_id" \
  -H "Content-Type: application/json" \
  -d "$preferences_payload" >/dev/null

curl --noproxy "*" -sS http://127.0.0.1:8012/users/me \
  -H "Authorization: Bearer $user_token" \
  -H "x-customer-id: $user_id" >/dev/null

echo "E2E DONE ✅"
