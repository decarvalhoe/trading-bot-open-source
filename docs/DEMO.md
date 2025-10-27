# Run Demo Guide

This guide walks you through spinning up the full Trading-Bot stack and executing the demo
scenario from registration to your first backtest. It covers workstation, WSL and
Codespaces setups and finishes with troubleshooting tips.

## Prerequisites

- **Docker** with Compose plugin (Docker Desktop on macOS/Windows, `docker-ce` on Linux).
- **Python 3.11+** for running helper scripts and tests locally.
- **Node.js 18+** *(optional)* if you plan to hack on the dashboard assets.
- At least 8 GB of RAM available for the containers.

## 1. Clone and bootstrap the repository

```bash
git clone https://github.com/<your-org>/trading-bot-open-source.git
cd trading-bot-open-source
python -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install --upgrade pip
pip install -r requirements-dev.txt
```

If you intend to exercise the web dashboard end-to-end tests, install Playwright assets once:

```bash
pip install -r services/web_dashboard/requirements-dev.txt
python -m playwright install --with-deps chromium
```

## 2. Start the demo stack

The `demo-up` target builds and launches every service required for the walkthrough, plus
Prometheus and Grafana for observability.

```bash
make demo-up
```

Services expose the following ports by default:

| Component | URL (host) | Purpose |
| --------- | ---------- | ------- |
| Web dashboard | http://localhost:8022 | End-user UI for onboarding, status and backtesting |
| Auth service | http://localhost:8011 | Account registration, login and token refresh |
| User service | http://localhost:8012 | Stores profile information and demo personas |
| Order router | http://localhost:8013 | Relays orders to the execution venues |
| Algo engine | http://localhost:8014 | Runs strategies and backtests |
| Reports service | http://localhost:8016 | Generates and serves performance reports |
| Grafana | http://localhost:3000 (admin/admin) | Observability dashboards |
| Prometheus | http://localhost:9090 | Metrics collection |

### Dashboard service bindings

The dashboard relies on a handful of environment variables to reach the backend services. When
you use `make demo-up` the compose file seeds the following defaults:

| Service | `WEB_DASHBOARD_*` variable | Default target | Host port exposed |
| ------- | ------------------------- | -------------- | ----------------- |
| Auth service | `WEB_DASHBOARD_AUTH_SERVICE_URL` | `http://auth_service:8000/` | `http://localhost:8011` |
| Reports service | `WEB_DASHBOARD_REPORTS_BASE_URL` | `http://reports:8000` | `http://localhost:8016` |
| Algo engine | `WEB_DASHBOARD_ALGO_ENGINE_URL` | `http://algo_engine:8000/` | `http://localhost:8014` |
| Order router | `WEB_DASHBOARD_ORDER_ROUTER_BASE_URL` | `http://order_router:8000/` | `http://localhost:8013` |
| Marketplace | `WEB_DASHBOARD_MARKETPLACE_URL` | `http://marketplace:8000/` | *(configure if enabled)* |

Adjust these variables in your environment or override them in `docker-compose.override.yml` when
pointing the dashboard at remote services.

### Streaming defaults consumed by demo services

`make demo-up` also wires the streaming ingest settings shared by `order-router`, `reports`, and the
dashboard:

| Variable | Default | Used by |
| -------- | ------- | ------- |
| `STREAMING_INGEST_URL` | `http://streaming:8000` | Order router, reports, streaming gateway |
| `STREAMING_SERVICE_TOKEN` | `reports-token` | Order router (ingest authentication) |
| `STREAMING_ROOM_ID` | `public-room` | Order router, dashboard widgets |

Keep these defaults aligned across `.env.dev` and your shell so every service receives consistent
values during local demos. Override them if you expose the streaming stack on a different host or
rotate the shared token.

### Database migration toggle

Containers built from `infra/docker/fastapi-service.Dockerfile` honour a `RUN_MIGRATIONS`
environment variable. It defaults to `1` (run Alembic on startup) via `.env.dev`, and
`docker-compose.yml` overrides it to `0` for stateless services such as `streaming`,
`streaming_gateway`, `inplay`, `notification_service`, and `web_dashboard`. Leave the flag enabled
for services backed by PostgreSQL (`billing_service`, `order_router`, `market_data`, `reports`,
`alert_engine`) so they apply schema updates automatically.

With the stack running you can seed demo credentials, entitlements and sample alerts directly from
the compose network:

```bash
make demo-bootstrap
```

The target now injects container-scoped URLs such as `http://auth_service:8000` and
`http://user_service:8000` so the helper talks to every service over the internal Docker network.
If you need to point the bootstrap script somewhere else, either pass the `--*-url` flags or export
`BOOTSTRAP_*` environment variables before invoking the command.

## 3. Walk through the demo

1. **Create an account via the dashboard.** Visit http://localhost:8022/account/register once the
   containers report ready. Fill in an email and a strong password, then submit the form. A success
   banner redirects you to the login page.
2. **Sign in.** Use the credentials you just created on http://localhost:8022/account/login.
   The top banner confirms you are authenticated (“Connecté en tant que …”).
3. **Check service health.** From the navigation menu open http://localhost:8022/status. The page
   calls the auth, reports, algo engine, order router and marketplace endpoints and marks each as
   “Opérationnel” when the corresponding `/health` probe answers.
4. **Launch a backtest from the UI.** Go to http://localhost:8022/strategies, pick the “ORB” demo
   strategy (or design your own), set the asset, timeframe, lookback window and initial balance, then
   click “Lancer le backtest”. Watch for the confirmation toast and the updated history card.
5. **Observe metrics.** Browse to http://localhost:3000, open the *Trading-Bot Overview* dashboard
   and confirm request rates, latency and error panels are populated.

Shut everything down with `make demo-down` when you are done.

## Optional: command-line registration and troubleshooting

The web flow is the recommended path. If you need to bootstrap accounts without the UI (for
automated tests, CI or air-gapped environments), you can still call the services directly:

```bash
curl -X POST http://localhost:8011/auth/register -H 'Content-Type: application/json' -d '{"email":"demo@example.com","password":"ValidPass123!"}'

export DEMO_TOKEN=$(python -c 'from datetime import datetime, timezone; from jose import jwt; print(jwt.encode({"sub": "auth_service", "iat": int(datetime.now(timezone.utc).timestamp())}, "test-onboarding-secret", algorithm="HS256"))')
curl -X POST http://localhost:8012/users/register -H "Authorization: Bearer $DEMO_TOKEN" -H 'Content-Type: application/json' -d '{"email":"demo@example.com","first_name":"Demo","last_name":"Trader"}'
```

Both endpoints return `{ "status": "ok" }` on success and let you confirm the underlying services
remain reachable even if the dashboard is unavailable.

## Running inside WSL

1. Install [Docker Desktop](https://docs.docker.com/desktop/install/windows-install/) and enable
   integration for your WSL distribution.
2. From your WSL shell, follow the same steps as the Linux walkthrough (`make demo-up`, open
   `http://localhost:8022/status`, browse the dashboard via `http://localhost:8022` from Windows or
   WSL).
3. If browsers cannot reach the services, ensure the WSL firewall allows inbound connections and
   that Docker Desktop is running.

## Running in GitHub Codespaces

1. Create a Codespace from the repository – the devcontainer already ships with Docker-in-Docker.
2. Inside the Codespace terminal run `make demo-up` and wait for all services to report healthy.
3. Use **Ports** forwarding to expose 8022 (dashboard), 8011 (auth) and 3000 (Grafana). The
   forwarded URLs appear automatically.
4. Execute the walkthrough exactly like on a workstation: register via `/account/register`, inspect
   `/status` and launch a backtest from `/strategies`. You can also run the automated flow with
   `pytest services/web_dashboard/tests/e2e/test_demo_journey.py -vv` once Playwright browsers are
   installed.

## Troubleshooting

| Symptom | Fix |
| ------- | --- |
| `curl` to `/health` hangs | Verify containers are running (`docker compose ps`). Restart an unhealthy service with `docker compose restart <service>`.
| Login fails with 401 | Ensure you registered the user in both auth-service and user-service and that the JWT secret matches (`JWT_SECRET=test-onboarding-secret`).
| Playwright complains about missing browsers | Run `python -m playwright install --with-deps chromium` in your virtualenv.
| Ports already in use | Edit `docker-compose.yml` port mappings or stop the conflicting process.
| Grafana dashboard empty | Check Prometheus scrape targets at http://localhost:9090/targets and confirm services expose `/metrics`.

With the stack healthy and the demo flow complete you now have a baseline environment for building
new trading strategies or extending the platform.
