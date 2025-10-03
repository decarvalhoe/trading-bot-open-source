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

| Service | URL |
| ------- | --- |
| Web dashboard | http://localhost:8022 |
| Auth service | http://localhost:8011 |
| User service | http://localhost:8004 |
| Algo engine | http://localhost:8020 |
| Grafana | http://localhost:3000 (admin/admin) |
| Prometheus | http://localhost:9090 |

Verify health probes once containers are up:

```bash
curl http://localhost:8022/health
curl http://localhost:8011/health
curl http://localhost:8004/health
```

All endpoints should return `{ "status": "ok" }`.

## 3. Walk through the demo

1. **Register** – call the auth service to provision credentials:
   ```bash
   curl -X POST http://localhost:8011/auth/register \
     -H 'Content-Type: application/json' \
     -d '{"email":"demo@example.com","password":"ValidPass123!"}'
   ```
2. **Create the user profile** – register the same email with user-service:
   ```bash
   export DEMO_TOKEN=$(python -c 'from datetime import datetime, timezone; from jose import jwt; print(jwt.encode({"sub": "auth-service", "iat": int(datetime.now(timezone.utc).timestamp())}, "test-onboarding-secret", algorithm="HS256"))')
   curl -X POST http://localhost:8004/users/register \
     -H "Authorization: Bearer $DEMO_TOKEN" \
     -H 'Content-Type: application/json' \
     -d '{"email":"demo@example.com","first_name":"Demo","last_name":"Trader"}'
   ```
3. **Login through the dashboard** – open http://localhost:8022/account and sign in with
   the credentials created in step 1. The “Connecté en tant que …” banner confirms the session.
4. **Onboarding dry-run** – navigate to http://localhost:8022/dashboard?user_id=<USER_ID> using the
   identifier returned by user-service. Click through “Connexion broker”, “Créer une stratégie” and
   “Premier backtest” to complete the checklist.
5. **Strategy & Backtest** – head to http://localhost:8022/strategies. Select the “ORB” strategy,
   choose your asset (e.g. ETHUSDT), tweak the inputs and trigger “Lancer le backtest”. A success
   toast and updated history confirm the run.
6. **Observe metrics** – browse to http://localhost:3000, open the *Trading-Bot Overview* dashboard
   and confirm request rates, latency and error panels are populated.

Shut everything down with `make demo-down` when you are done.

## Running inside WSL

1. Install [Docker Desktop](https://docs.docker.com/desktop/install/windows-install/) and enable
   integration for your WSL distribution.
2. From your WSL shell, follow the same steps as the Linux walkthrough (`make demo-up`, curl health
   endpoints, open the dashboard via `http://localhost:8022` from Windows or WSL).
3. If browsers cannot reach the services, ensure the WSL firewall allows inbound connections and
   that Docker Desktop is running.

## Running in GitHub Codespaces

1. Create a Codespace from the repository – the devcontainer already ships with Docker-in-Docker.
2. Inside the Codespace terminal run `make demo-up` and wait for all services to report healthy.
3. Use **Ports** forwarding to expose 8022 (dashboard), 8011 (auth) and 3000 (Grafana). The
   forwarded URLs appear automatically.
4. Execute the walkthrough exactly like on a workstation. You can also run the automated flow with
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
