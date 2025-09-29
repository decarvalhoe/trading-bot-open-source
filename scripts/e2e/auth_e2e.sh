set -euo pipefail
export NO_PROXY="localhost,127.0.0.1"; export no_proxy="$NO_PROXY"

curl --noproxy "*" -sf http://127.0.0.1:8011/health >/dev/null
curl --noproxy "*" -sf http://127.0.0.1:8012/health >/dev/null

email="dev$(date +%Y%m%d%H%M%S)@example.com"
password="Passw0rd!"

curl --noproxy "*" -sS -X POST http://127.0.0.1:8011/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$email\",\"password\":\"$password\"}" >/dev/null

login_response=$(curl --noproxy "*" -sS -X POST http://127.0.0.1:8011/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$email\",\"password\":\"$password\"}")

token=$(python -c "import sys,json; print(json.load(sys.stdin)['access_token'])" <<<"$login_response")
refresh=$(python -c "import sys,json; print(json.load(sys.stdin)['refresh_token'])" <<<"$login_response")

curl --noproxy "*" -sS -H "Authorization: Bearer $token" http://127.0.0.1:8011/auth/me >/dev/null

setup_response=$(curl --noproxy "*" -sS -H "Authorization: Bearer $token" http://127.0.0.1:8011/auth/totp/setup)
secret=$(python -c "import sys,json; print(json.load(sys.stdin)['secret'])" <<<"$setup_response")

invalid_status=$(curl --noproxy "*" -sS -o /tmp/totp-invalid.json -w "%{http_code}" \
  -H "Authorization: Bearer $token" \
  "http://127.0.0.1:8011/auth/totp/enable?code=000000")
if [ "$invalid_status" -ne 400 ]; then
  echo "Expected 400 when enabling TOTP with an invalid code" >&2
  exit 1
fi

valid_code=$(python - <<PY
import sys
import pyotp
print(pyotp.TOTP(sys.argv[1]).now())
PY
"$secret")

curl --noproxy "*" -sS -H "Authorization: Bearer $token" \
  "http://127.0.0.1:8011/auth/totp/enable?code=$valid_code" >/dev/null

missing_status=$(curl --noproxy "*" -sS -o /tmp/totp-login-missing.json -w "%{http_code}" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$email\",\"password\":\"$password\"}" \
  -X POST http://127.0.0.1:8011/auth/login)
if [ "$missing_status" -ne 401 ]; then
  echo "Login without TOTP should be rejected" >&2
  exit 1
fi

totp_code=$(python - <<PY
import sys
import pyotp
print(pyotp.TOTP(sys.argv[1]).now())
PY
"$secret")

login_with_totp=$(curl --noproxy "*" -sS -X POST http://127.0.0.1:8011/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$email\",\"password\":\"$password\",\"totp\":\"$totp_code\"}")

token=$(python -c "import sys,json; print(json.load(sys.stdin)['access_token'])" <<<"$login_with_totp")

regen_response=$(curl --noproxy "*" -sS -H "Authorization: Bearer $token" http://127.0.0.1:8011/auth/totp/setup)
new_secret=$(python -c "import sys,json; print(json.load(sys.stdin)['secret'])" <<<"$regen_response")

if [ "$new_secret" = "$secret" ]; then
  echo "TOTP regeneration did not issue a new secret" >&2
  exit 1
fi

old_code=$(python - <<PY
import sys
import pyotp
print(pyotp.TOTP(sys.argv[1]).now())
PY
"$secret")

old_login_status=$(curl --noproxy "*" -sS -o /tmp/totp-login-old.json -w "%{http_code}" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$email\",\"password\":\"$password\",\"totp\":\"$old_code\"}" \
  -X POST http://127.0.0.1:8011/auth/login)
if [ "$old_login_status" -ne 401 ]; then
  echo "Login with stale TOTP should fail" >&2
  exit 1
fi

new_code=$(python - <<PY
import sys
import pyotp
print(pyotp.TOTP(sys.argv[1]).now())
PY
"$new_secret")

curl --noproxy "*" -sS -H "Authorization: Bearer $token" \
  "http://127.0.0.1:8011/auth/totp/enable?code=$new_code" >/dev/null

final_code=$(python - <<PY
import sys
import pyotp
print(pyotp.TOTP(sys.argv[1]).now())
PY
"$new_secret")

final_login=$(curl --noproxy "*" -sS -X POST http://127.0.0.1:8011/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$email\",\"password\":\"$password\",\"totp\":\"$final_code\"}")

python -c "import sys,json; json.load(sys.stdin)" <<<"$final_login" >/dev/null

token=$(python -c "import sys,json; print(json.load(sys.stdin)['access_token'])" <<<"$final_login")

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
payload = {"sub": $user_id, "iat": now}
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
