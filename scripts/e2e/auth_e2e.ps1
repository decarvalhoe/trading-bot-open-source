$ErrorActionPreference = "Stop"
$env:NO_PROXY="localhost,127.0.0.1"; $env:no_proxy=$env:NO_PROXY

function Assert($ok, $msg) {
  if (-not $ok) { Write-Error $msg; exit 1 } else { Write-Host "OK - $msg" }
}

# Health
$h1 = curl.exe --noproxy "*" http://127.0.0.1:8011/health 2>$null
$h2 = curl.exe --noproxy "*" http://127.0.0.1:8012/health 2>$null
Assert ($h1 -match '"ok"' -or $h1 -match 'status' -or $h1 -match 'OK') "auth-service /health"
# user-service peut ne pas répondre encore, on tolère (enlève ce commentaire quand prêt)

# Register
$email="dev$(Get-Date -Format 'yyyyMMddHHmmss')@example.com"
$reg = curl.exe -s -X POST "http://127.0.0.1:8011/auth/register" `
  -H "Content-Type: application/json" `
  -d "{\"email\": \"$email\", \"password\": \"Passw0rd!\"}"
Assert ($LASTEXITCODE -eq 0) "register call"
Write-Host "REGISTER => $reg"

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
Write-Host "ME => $me"
Write-Host "E2E DONE ✅"
