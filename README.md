[English](README.md) | [Français](README.fr.md)

# 🤖 Open Source Trading Bot

An automated and intelligent trading bot, designed to be **transparent**, **secure**, and **scalable**. This open-source project allows traders of all levels to automate their trading strategies with modern and reliable technology.

## 🎯 What is this project?

This trading bot is a complete platform that allows you to:

- **Automate your trading strategies** on different financial markets
- **Manage your risks** with customizable parameters
- **Track your performance** in real-time with detailed dashboards
- **Collaborate** with a community of traders and developers

### Why choose this bot?

- ✅ **100% Open Source**: Transparent and auditable code
- ✅ **Enhanced Security**: Robust authentication and data protection
- ✅ **Modern Architecture**: Scalable and maintainable microservices
- ✅ **Ease of Use**: Intuitive interface and complete documentation
- ✅ **Active Community**: Continuous support and contributions

## 🧭 Feature overview

| Domain | Scope | Status | Activation prerequisites |
| --- | --- | --- | --- |
| Strategies & research | Visual Strategy Designer, declarative imports, AI assistant, backtesting API | Delivered (designer & backtests), Beta opt-in (assistant) | `make demo-up`, `pip install -r services/algo-engine/requirements.txt`, `AI_ASSISTANT_ENABLED=1`, `OPENAI_API_KEY` |
| Trading & execution | Sandbox order router, strategy bootstrap script, market connectors (Binance, IBKR, DTC stub) | Delivered (sandbox + Binance/IBKR), Experimental (DTC) | `scripts/dev/bootstrap_demo.py`, connector credentials when available |
| Real-time monitoring | Streaming gateway, InPlay WebSocket feed, OBS/overlay integrations | Delivered (dashboard + alerts), Beta (OBS automation) | Service tokens (`reports`, `inplay`, `streaming`), optional OAuth secrets |
| Reporting & analytics | Daily reports API, PDF exports, risk metrics | Delivered (reports), In progress (extended risk dashboards) | Ensure `data/generated-reports/` is writable; enable Prometheus/Grafana stack |
| Notifications & alerts | Alert engine, multi-channel notification service (Slack, email, Telegram, SMS) | Delivered (core delivery), Beta (templates/throttling) | Configure channel-specific environment variables; keep `NOTIFICATION_SERVICE_DRY_RUN` for staging |
| Marketplace & onboarding | Listings API with Stripe Connect splits, copy-trading subscriptions, onboarding automation | Beta private launch | Stripe Connect account, entitlements via billing service |

Track detailed milestones and owners in
[`docs/release-highlights/2025-12.md`](docs/release-highlights/2025-12.md).

## 🚀 Project Status

### Phase 1: Foundations (✅ Completed)
**Objective**: To set up the basic technical infrastructure

- ✅ **Project Setup**: Repository, development tools, CI/CD

```bash
# 1. Clone the project
git clone https://github.com/decarvalhoe/trading-bot-open-source.git
cd trading-bot-open-source

# 2. Install development tools
make setup

# 3. Start the development environment
make dev-up

# 4. Check that everything is working (auth-service health)
curl http://localhost:8011/health

# 5. Stop the environment
make dev-down
```

### Demo trading stack

To explore the monitoring and alerting services together, start the full demo stack:

```bash
make demo-up
```

The command builds the additional FastAPI services, applies Alembic migrations and wires
Redis/PostgreSQL before exposing the following ports. Enable the optional AI strategy
assistant and connectors with:

```bash
pip install -r services/algo-engine/requirements.txt
export AI_ASSISTANT_ENABLED=1
export OPENAI_API_KEY="sk-your-key"
```

- `8013` — `order-router` (execution plans and simulated brokers)
- `8014` — `algo-engine` (strategy catalogue, backtesting, optional AI assistant on `/strategies/generate`)
- `8015` — `market_data` (spot quotes, orderbooks and TradingView webhooks)
- `8016` — `reports` (risk reports and PDF generation)
- `8017` — `alert_engine` (rule evaluation with streaming ingestion)
- `8018` — `notification-service` (alert delivery history)
- `8019` — `streaming` (room ingest + WebSocket fan-out)
- `8020` — `streaming_gateway` (overlay OAuth flows and TradingView bridge)
- `8021` — `inplay` (watchlist WebSocket updates)
- `8022` — `web-dashboard` (HTML dashboard backed by reports + alerts APIs)

Generated artefacts are stored in `data/generated-reports/` (PDF exports) and
`data/alert-events/` (shared SQLite database for alerts history). Default service tokens
(`reports-token`, `inplay-token`, `demo-alerts-token`) and external API secrets can be
overridden through environment variables before running the stack. Stop every container
with:

```bash
make demo-down
```

#### Bootstrap the end-to-end flow

Once the stack is running you can exercise the full onboarding → trading journey with
the helper script:

```bash
scripts/dev/bootstrap_demo.py BTCUSDT 0.25 --order-type market
```

The command provisions a demo account, assigns entitlements, configures a strategy,
routes an order, generates a PDF report, registers an alert and publishes a streaming
event. The emitted JSON summarises all created identifiers (user, strategy, order,
alert, report location) together with the JWT tokens associated to the demo profile.
Replay the flow interactively with the notebook in
[`docs/tutorials/backtest-sandbox.ipynb`](docs/tutorials/backtest-sandbox.ipynb).
`scripts/dev/run_mvp_flow.py` now simply wraps this command for backward compatibility.

### Database migrations

Use the Makefile helpers to manage Alembic migrations locally (the commands default to
`postgresql+psycopg2://trading:trading@localhost:5432/trading`, override it with
`ALEMBIC_DATABASE_URL=<your-url>` when needed):

```bash
# Generate a new revision
make migrate-generate message="add user preferences"

# Generate a trading revision directly with Alembic (autogenerates orders/executions models)
ALEMBIC_DATABASE_URL=postgresql+psycopg2://trading:trading@localhost:5432/trading \
  alembic -c infra/migrations/alembic.ini revision --autogenerate -m "add trading orders and executions tables"

# Apply migrations (defaults to head)
make migrate-up

# Roll back the previous revision (override DOWN_REVISION to target another one)
make migrate-down
```

Docker services now apply migrations automatically during startup through
[`scripts/run_migrations.sh`](scripts/run_migrations.sh), ensuring the database schema is
up to date before each application boots.

### Technical Architecture

The project uses a modern **microservices architecture**:

- **Business Services**: Each feature is an independent service
- **Database**: PostgreSQL for data persistence
- **Cache**: Redis for performance
- **API**: FastAPI for fast and documented interfaces
- **Containerization**: Docker for simplified deployment

### Project Structure

```
trading-bot-open-source/
├── services/           # Business services (authentication, trading, etc.)
├── infra/             # Infrastructure (database, migrations)
├── libs/              # Shared libraries
├── scripts/           # Automation scripts
└── docs/              # Documentation
```

## 🤝 How to Contribute?

We welcome all contributions! Whether you are:

- **Experienced Trader**: Share your strategies and expertise
- **Developer**: Improve the code and add new features
- **Tester**: Help us identify and fix bugs
- **Designer**: Improve the user experience

### Steps to Contribute

1. **Consult** the [open issues](https://github.com/decarvalhoe/trading-bot-open-source/issues)
2. **Read** the contribution guide in `CONTRIBUTING.md`
3. **Create** a branch for your contribution
4. **Submit** a pull request with your improvements

## 📊 2025 Review & Next Steps

A complete technical review of the repository was conducted in November 2025. It confirms the strength of the current architecture (FastAPI microservices, shared entitlements middleware) and highlights the priority initiatives needed to deliver an operational trading journey.

- **Key strengths**: advanced authentication foundation (TOTP MFA, roles), observability stack (logs + Prometheus/Grafana), onboarding-friendly Makefile, structured documentation.
- **Watch points**: trading services still rely on in-memory state, limited multi-service test coverage, secret-management operations to formalize.
- **Recommended priorities (0-3 months)**: consolidate auth/user E2E documentation, persist trading artefacts, expand testing (unit + contract), publish secret rotation and observability playbooks.

Find the detailed review, roadmap and backlog in:

- [`docs/reports/2025-11-code-review.md`](docs/reports/2025-11-code-review.md)
- [`docs/project-evaluation.md`](docs/project-evaluation.md)
- [`docs/tasks/2025-q4-backlog.md`](docs/tasks/2025-q4-backlog.md)

## 📞 Support and Community

- **GitHub Issues**: To report bugs or suggest features
- **Discussions**: To interact with the community
- **Documentation**: Complete guide in the `docs/` folder

## 📄 License

This project is licensed under the MIT License - see the `LICENSE` file for more details.

---

> **Developed with ❤️ by decarvalhoe and the open-source community**
> Last updated: November 2025
- ✅ **Configuration Service**: Centralized parameter management

*Result*: The technical infrastructure is operational and ready for development.

### Phase 2: Authentication and Users (✅ Completed)
**Objective**: To allow users to create accounts and log in securely

- ✅ **Authentication System**: Registration, login, JWT security, MFA TOTP
- ✅ **Profile Management**: Creation and modification of user profiles with entitlement-based masking
- ✅ **End-to-End Documentation**: Consolidated OpenAPI specs and UX guides for a full onboarding path

*Result*: Users can create secure accounts, activate their profile and prepare for MFA enrolment.

### Phase 3: Trading Strategies (🔄 In Progress - 80%)
**Objective**: To allow the creation and execution of trading strategies

- ✅ **Strategy Engine**: In-memory catalogue, declarative import and backtesting API
- ✅ **Visual Designer (beta)**: Web dashboard canvas exporting YAML/Python definitions compatible with the importer
- 🟡 **AI Strategy Assistant (opt-in beta)**: Enable `/strategies/generate` with LangChain/OpenAI once environment variables are set
- ✅ **Market Connectors**: Sandbox adapters for Binance/IBKR with shared limits; Sierra Chart DTC stub remains experimental
- 🔄 **Order Management**: Persistence and execution history implementation in progress

### Phase 4: Monitoring and Analytics (🔄 In Progress - 53%)
**Objective**: To provide tools for performance analysis and tracking

- ✅ **Real-time dashboards**: Streaming gateway + InPlay feed powering live setups, portfolio deltas and alert lists
- ✅ **Reports Service** (65%): Performance metrics calculations, PDF exports and API endpoints consumed by the dashboard
- 🟡 **Notifications Service** (45%): Multi-channel delivery (Slack/email/Telegram/SMS) available with dry-run safeguards
- 🟡 **Observability Infrastructure** (70%): Prometheus/Grafana dashboards online; overlay automation for OBS targeted for Q1 2026

*Next Steps*: Harden notification throttling, enrich Grafana packs, and document OBS automation best practices.

## 📊 Project Metrics (September 2025)

- **Lines of Code**: 17,676 (Python only)
- **Number of Services**: 20 microservices
- **Number of Commits**: 129
- **Number of Tests**: 26 unit test files
- **Contributors**: 2 active developers

## 🗺️ Roadmap and Next Steps

### Short-term Priorities (0-1 month)

1. **Finalize Phase 4: Monitoring and Analytics**
   - Complete the notifications service with unit tests
   - Enhance the web dashboard with more visualizations
   - Configure alerts in Prometheus/Grafana
   - Integrate all Phase 4 services in docker-compose.yml

2. **Improve Documentation**
   - Consolidate OpenAPI documentation for all services
   - Create user guides for monitoring features
   - Document operational procedures for alert management

### Medium-term Goals (1-3 months)

1. **Performance Optimization**
   - Improve strategy engine performance
   - Optimize database queries
   - Implement a distributed cache system

2. **Extend Market Connectors**
   - Add new connectors for other exchanges
   - Implement adapters for traditional markets
   - Improve rate limit management

3. **Strategy Enrichment**
   - Develop a library of ready-to-use strategies
   - Create a visual strategy editor
   - Implement advanced backtesting tools

## 🌟 Release highlights & tutorials

- Review consolidated milestones and status owners in [docs/release-highlights/2025-12.md](docs/release-highlights/2025-12.md).
- Updated notebooks and videos are listed in [docs/tutorials/README.md](docs/tutorials/README.md) for quick onboarding.
- Service sign-offs and communication log reside under [docs/governance/release-approvals/2025-12.md](docs/governance/release-approvals/2025-12.md) and [docs/communications/2025-12-release-update.md](docs/communications/2025-12-release-update.md).

## 🛠️ For Developers
