$ErrorActionPreference = "Stop"
$env:NO_PROXY="localhost,127.0.0.1"; $env:no_proxy=$env:NO_PROXY

function Assert($ok, $msg) {
  if (-not $ok) { Write-Error $msg; exit 1 } else { Write-Host "OK - $msg" }
}

# Health
$h1 = curl.exe --noproxy "*" http://127.0.0.1:8011/health 2>$null
$h2 = curl.exe --noproxy "*" http://127.0.0.1:8012/health 2>$null
Assert ($h1 -match '"ok"' -or $h1 -match 'status' -or $h1 -match 'OK') "auth-service /health"
Assert ($h2 -match '"ok"' -or $h2 -match 'status' -or $h2 -match 'OK') "user-service /health"

# Register
$email="dev$(Get-Date -Format 'yyyyMMddHHmmss')@example.com"
$reg = curl.exe -s -X POST "http://127.0.0.1:8011/auth/register" `
  -H "Content-Type: application/json" `
  -d "{\"email\": \"$email\", \"password\": \"Passw0rd!\"}"
Assert ($LASTEXITCODE -eq 0) "register call"
$regJson = $reg | ConvertFrom-Json
$authUserId = $regJson.id

# Login
$login = curl.exe -s -X POST "http://127.0.0.1:8011/auth/login" `
  -H "Content-Type: application/json" `
  -d "{\"email\": \"$email\", \"password\": \"Passw0rd!\"}"
Assert ($LASTEXITCODE -eq 0) "login call"
$json = $login | ConvertFrom-Json
$token = $json.access_token
Assert ($token) "access_token extracted"

# Me
$me = curl.exe -s -H "Authorization: Bearer $token" "http://127.0.0.1:8011/auth/me"
Assert ($LASTEXITCODE -eq 0) "/auth/me call"

# TOTP setup
$setup = curl.exe -s -H "Authorization: Bearer $token" "http://127.0.0.1:8011/auth/totp/setup"
$setupJson = $setup | ConvertFrom-Json
$secret = $setupJson.secret
Assert ($secret) "TOTP secret received"

$invalidStatus = curl.exe --noproxy "*" -s -o $env:TEMP\totp-invalid.json -w "%{http_code}" `
  -H "Authorization: Bearer $token" `
  "http://127.0.0.1:8011/auth/totp/enable?code=000000"
Assert ($invalidStatus -eq 400) "invalid TOTP rejected"

$validCode = python -c "import sys,pyotp; print(pyotp.TOTP(sys.argv[1]).now())" $secret
curl.exe -s -H "Authorization: Bearer $token" "http://127.0.0.1:8011/auth/totp/enable?code=$validCode" | Out-Null

$missingStatus = curl.exe --noproxy "*" -s -o $env:TEMP\totp-missing.json -w "%{http_code}" `
  -H "Content-Type: application/json" `
  -d "{\"email\": \"$email\", \"password\": \"Passw0rd!\"}" `
  -X POST "http://127.0.0.1:8011/auth/login"
Assert ($missingStatus -eq 401) "login without TOTP rejected"

$totpCode = python -c "import sys,pyotp; print(pyotp.TOTP(sys.argv[1]).now())" $secret
$loginTotp = curl.exe -s -X POST "http://127.0.0.1:8011/auth/login" `
  -H "Content-Type: application/json" `
  -d "{\"email\": \"$email\", \"password\": \"Passw0rd!\", \"totp\": \"$totpCode\"}"
$jsonTotp = $loginTotp | ConvertFrom-Json
$token = $jsonTotp.access_token
Assert ($token) "TOTP login succeeded"

$regen = curl.exe -s -H "Authorization: Bearer $token" "http://127.0.0.1:8011/auth/totp/setup"
$regenJson = $regen | ConvertFrom-Json
$newSecret = $regenJson.secret
Assert ($newSecret -and $newSecret -ne $secret) "TOTP secret regenerated"

$oldCode = python -c "import sys,pyotp; print(pyotp.TOTP(sys.argv[1]).now())" $secret
$oldStatus = curl.exe --noproxy "*" -s -o $env:TEMP\totp-old.json -w "%{http_code}" `
  -H "Content-Type: application/json" `
  -d "{\"email\": \"$email\", \"password\": \"Passw0rd!\", \"totp\": \"$oldCode\"}" `
  -X POST "http://127.0.0.1:8011/auth/login"
Assert ($oldStatus -eq 401) "stale TOTP rejected"

$newCode = python -c "import sys,pyotp; print(pyotp.TOTP(sys.argv[1]).now())" $newSecret
curl.exe -s -H "Authorization: Bearer $token" "http://127.0.0.1:8011/auth/totp/enable?code=$newCode" | Out-Null

$finalCode = python -c "import sys,pyotp; print(pyotp.TOTP(sys.argv[1]).now())" $newSecret
$finalLogin = curl.exe -s -X POST "http://127.0.0.1:8011/auth/login" `
  -H "Content-Type: application/json" `
  -d "{\"email\": \"$email\", \"password\": \"Passw0rd!\", \"totp\": \"$finalCode\"}"
$finalJson = $finalLogin | ConvertFrom-Json
$token = $finalJson.access_token
Assert ($token) "final login after regeneration"

# User service registration
$userPayload = @{ email = $email; display_name = "Dev User" } | ConvertTo-Json
$userResponse = curl.exe -s -X POST "http://127.0.0.1:8012/users/register" `
  -H "Content-Type: application/json" `
  -d $userPayload
Assert ($LASTEXITCODE -eq 0) "user-service register"
$userJson = $userResponse | ConvertFrom-Json
$userId = $userJson.id

$userToken = python -c "import os,sys; from datetime import datetime, timezone; from jose import jwt; secret=os.getenv('JWT_SECRET','dev-secret-change-me'); now=int(datetime.now(timezone.utc).timestamp()); print(jwt.encode({'sub': sys.argv[1], 'iat': now}, secret, algorithm='HS256'))" $userId
Assert ($LASTEXITCODE -eq 0 -and $userToken) "user token generation"

$headers = @{ "Authorization" = "Bearer $userToken"; "x-customer-id" = "$userId" }

# Activate
$activate = curl.exe -s -X POST "http://127.0.0.1:8012/users/$userId/activate" `
  -H "Authorization: Bearer $userToken" `
  -H "x-customer-id: $userId"
Assert ($LASTEXITCODE -eq 0) "user activation"

# Profile update
$profilePayload = @{ display_name = "Dev Trader"; full_name = "Developer Example"; locale = "fr_FR"; marketing_opt_in = $true } | ConvertTo-Json
$profile = curl.exe -s -X PATCH "http://127.0.0.1:8012/users/$userId" `
  -H "Authorization: Bearer $userToken" `
  -H "x-customer-id: $userId" `
  -H "Content-Type: application/json" `
  -d $profilePayload
Assert ($LASTEXITCODE -eq 0) "profile update"

# Preferences
$prefsPayload = @{ preferences = @{ theme = "dark"; currency = "EUR" } } | ConvertTo-Json
$prefs = curl.exe -s -X PUT "http://127.0.0.1:8012/users/me/preferences" `
  -H "Authorization: Bearer $userToken" `
  -H "x-customer-id: $userId" `
  -H "Content-Type: application/json" `
  -d $prefsPayload
Assert ($LASTEXITCODE -eq 0) "preferences update"

# Me (user service)
$meUser = curl.exe -s "http://127.0.0.1:8012/users/me" `
  -H "Authorization: Bearer $userToken" `
  -H "x-customer-id: $userId"
Assert ($LASTEXITCODE -eq 0) "user-service /users/me"

Write-Host "E2E DONE ✅"
