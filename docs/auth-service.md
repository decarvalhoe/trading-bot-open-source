# Auth Service Configuration

The **auth-service** issues JWTs, manages user credentials and enforces
entitlements on every request. Deployments can tune several
configuration switches through environment variables. The service reads
them during startup without requiring a rebuild.

## CORS controls

When embedding the authentication APIs behind a web frontend you must
configure the Cross-Origin Resource Sharing (CORS) policy so browsers
can call the endpoints. The following variables drive the middleware
layer:

| Variable | Description | Default |
| --- | --- | --- |
| `AUTH_SERVICE_ALLOWED_ORIGINS` | Comma-separated list of origins that are allowed to call the API. Use `*` to accept every origin or restrict it to your frontend domain. | `http://localhost:3000,http://localhost:8022` |
| `AUTH_SERVICE_ALLOWED_METHODS` | HTTP methods forwarded in the `Access-Control-Allow-Methods` header. | `GET,POST,PUT,PATCH,DELETE,OPTIONS` |
| `AUTH_SERVICE_ALLOWED_HEADERS` | Request headers exposed by the pre-flight response. | `Authorization,Content-Type` |
| `AUTH_SERVICE_ALLOW_CREDENTIALS` | Whether browsers can attach cookies or authorization headers. Accepts `1/0`, `true/false`, `yes/no`. | `true` |

### Example override

```bash
export AUTH_SERVICE_ALLOWED_ORIGINS="https://app.example.com"
export AUTH_SERVICE_ALLOWED_METHODS="GET,POST"
uvicorn services.auth_service.app.main:app --reload --port 8011
```

Once the service is running, confirm that the response advertises the
expected headers:

```bash
curl -i -H "Origin: https://app.example.com" http://localhost:8011/health
```

The command should include `Access-Control-Allow-Origin:
https://app.example.com` in the response, proving that the frontend will
be authorised by browsers.
