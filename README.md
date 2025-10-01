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
Redis/PostgreSQL before exposing the following ports:

- `8013` — `order-router` (execution plans and simulated brokers)
- `8014` — `algo-engine` (strategy catalogue and backtesting)
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
- ✅ **Market Connectors**: Sandbox adapters for Binance/IBKR with shared limits
- 🔄 **Order Management**: Persistence and execution history implementation in progress

### Phase 4: Monitoring and Analytics (🔄 In Progress - 53%)
**Objective**: To provide tools for performance analysis and tracking

- 🔄 **Reports Service** (65%): Performance metrics calculations, API and unit tests
- 🔄 **Notifications Service** (45%): Dispatcher, configuration and data schemas
- 🔄 **Web Dashboard** (50%): React components, streaming integration and metrics display
- 🔄 **Observability Infrastructure** (70%): Prometheus/Grafana configuration and FastAPI dashboard

*Next Steps*: Finalization of notification services, enhancement of web dashboard, and alert configuration.

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

## 🛠️ For Developers
