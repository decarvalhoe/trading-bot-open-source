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

## 🛠️ Technical Architecture

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

## 🧭 Feature Overview

| Domain | Scope | Status | Activation Prerequisites |
| --- | --- | --- | --- |
| Strategies & research | Visual Strategy Designer, declarative imports, AI assistant, backtesting API | Delivered (designer & backtests), Beta opt-in (assistant) | `make demo-up`, `pip install -r services/algo_engine/requirements.txt`, `AI_ASSISTANT_ENABLED=1`, `OPENAI_API_KEY` |
| Trading & execution | Sandbox order router, strategy bootstrap script, market connectors (Binance, IBKR, DTC stub) | Delivered (sandbox + Binance/IBKR), Experimental (DTC) | `scripts/dev/bootstrap_demo.py`, connector credentials when available |
| Real-time monitoring | Streaming gateway, InPlay WebSocket feed, OBS/overlay integrations | Delivered (dashboard + alerts), Beta (OBS automation) | Service tokens (`reports`, `inplay`, `streaming`), optional OAuth secrets |
| Reporting & analytics | Daily reports API, PDF exports, risk metrics | Delivered (reports), In progress (extended risk dashboards) | Ensure `data/generated-reports/` is writable; enable Prometheus/Grafana stack |
| Notifications & alerts | Alert engine, multi-channel notification service (Slack, email, Telegram, SMS) | Delivered (core delivery), Beta (templates/throttling) | Configure channel-specific environment variables; keep `NOTIFICATION_SERVICE_DRY_RUN` for staging |
| Marketplace & onboarding | Listings API with Stripe Connect splits, copy-trading subscriptions, onboarding automation | Beta private launch | Stripe Connect account, entitlements via billing service |

Track detailed milestones and owners in [`docs/release-highlights/2025-12.md`](docs/release-highlights/2025-12.md).

## 🚀 Quick Start

### Basic Setup

**Prerequisites:**

- [Docker](https://docs.docker.com/get-docker/) (default workflow), **or** native installations of `postgresql` (providing `pg_ctl`, `pg_isready`, `initdb`) and `redis` (`redis-server`, `redis-cli`).

```bash
# 1. Clone the project
git clone https://github.com/decarvalhoe/trading-bot-open-source.git
cd trading-bot-open-source

# 2. Install development tools
make setup

# 3. Start the development environment (Docker)
make dev-up

# 4. Check that everything is working (auth-service health)
curl http://localhost:8011/health

# 5. Stop the environment
make dev-down
```

### Native (host) development

The default `.env.dev` assumes every dependency runs inside Docker. When you
prefer to run PostgreSQL/Redis/RabbitMQ directly on your machine, switch to the
native configuration helpers:

```bash
# Point the stack at localhost services
export $(cat .env.native | grep -v '^#' | xargs)

# Make sure ENVIRONMENT=native so shared helpers hand out localhost URLs
echo $ENVIRONMENT  # native

# Apply the latest migrations against your host database
scripts/run_migrations.sh
```

Both the configuration service and the shared helpers use the
`ENVIRONMENT` flag to pick the right `.env.<env>` file and config JSON. Setting
`ENVIRONMENT=native` automatically rewrites DSNs such as `POSTGRES_DSN`,
`DATABASE_URL`, `REDIS_URL` and `RABBITMQ_URL` to target `localhost` while the
Docker-based environments keep pointing at the internal container hostnames.

The native `.env` also ships overrides for the web dashboard proxies so FastAPI
targets the host services directly:

- `WEB_DASHBOARD_AUTH_SERVICE_URL` / `AUTH_BASE_URL` → `http://localhost:8011`
- `WEB_DASHBOARD_USER_SERVICE_URL` → `http://localhost:8012`
- `WEB_DASHBOARD_ORDER_ROUTER_BASE_URL` / `ORDER_ROUTER_BASE_URL` →
  `http://localhost:8013`
- `WEB_DASHBOARD_ALGO_ENGINE_URL` / `ALGO_ENGINE_BASE_URL` →
  `http://localhost:8014`
- `MARKET_DATA_BASE_URL` → `http://localhost:8015`
- `WEB_DASHBOARD_REPORTS_BASE_URL` / `REPORTS_BASE_URL` →
  `http://localhost:8016`
- `WEB_DASHBOARD_ALERT_ENGINE_URL` → `http://localhost:8017`

### Demo Trading Stack

To explore the monitoring and alerting services together, start the full demo stack:

```bash
make demo-up
```

The command builds the additional FastAPI services, applies Alembic migrations and wires Redis/PostgreSQL before exposing the following ports. Enable the optional AI strategy assistant and connectors with:

```bash
pip install -r services/algo_engine/requirements.txt
export AI_ASSISTANT_ENABLED=1
export OPENAI_API_KEY="sk-your-key"
```

**Available Services:**
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

Generated artefacts are stored in `data/generated-reports/` (PDF exports) and `data/alert-events/` (shared SQLite database for alerts history). Default service tokens (`reports-token`, `inplay-token`, `demo-alerts-token`) and external API secrets can be overridden through environment variables before running the stack.

Stop every container with:

```bash
make demo-down
```

### Bootstrap the End-to-End Flow

Once the stack is running you can exercise the full onboarding → trading journey with the helper script:

```bash
scripts/dev/bootstrap_demo.py BTCUSDT 0.25 --order-type market
```

The command provisions a demo account, assigns entitlements, configures a strategy, routes an order, generates a PDF report, registers an alert and publishes a streaming event. The emitted JSON summarises all created identifiers (user, strategy, order, alert, report location) together with the JWT tokens associated to the demo profile.

`scripts/dev/run_mvp_flow.py` now simply wraps this command for backward compatibility.

### Database Migrations

Use the Makefile helpers to manage Alembic migrations locally (the commands default to `postgresql+psycopg2://trading:trading@localhost:5432/trading`, override it with `ALEMBIC_DATABASE_URL=<your-url>` when needed):

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

Docker services now apply migrations automatically during startup through [`scripts/run_migrations.sh`](scripts/run_migrations.sh), ensuring the database schema is up to date before each application boots.

## 📈 Project Status

### Phase 1: Foundations (✅ Completed)
**Objective**: To set up the basic technical infrastructure

- ✅ **Project Setup**: Repository, development tools, CI/CD
- ✅ **Configuration Service**: Centralized parameter management

*Result*: The technical infrastructure is operational and ready for development.

### Phase 2: Authentication and Users (✅ Completed)
**Objective**: To allow users to create accounts and log in securely

- ✅ **Authentication System**: Registration, login, JWT security, MFA TOTP
- ✅ **Profile Management**: Creation and modification of user profiles with entitlement-based masking
- ✅ **End-to-End Documentation**: Consolidated OpenAPI specs and UX guides for a full onboarding path

*Result*: Users can create secure accounts, activate their profile and prepare for MFA enrolment.

### Phase 3: Trading Strategies (✅ Completed)
**Objective**: To allow the creation and execution of trading strategies

- ✅ **Strategy Engine**: Persistent catalogue, declarative import and backtesting API
- ✅ **Visual Strategy Designer**: Drag-and-drop interface for strategy creation
- ✅ **AI Strategy Assistant**: OpenAI-powered strategy generation from natural language
- ✅ **Market Connectors**: Sandbox adapters for Binance/IBKR with shared limits
- ✅ **Order Management**: Persistence and execution history implementation

### Phase 4: Monitoring and Analytics (✅ Completed)
**Objective**: To provide tools for performance analysis and tracking

- ✅ **Reports Service**: Performance metrics calculations, API and unit tests
- ✅ **Notifications Service**: Multi-channel dispatcher with Slack, email, Telegram, SMS support
- ✅ **Web Dashboard**: React components, streaming integration and metrics display
- ✅ **Observability Infrastructure**: Prometheus/Grafana configuration and FastAPI dashboard

### Phase 5: Marketplace and Community (🔄 Beta)
**Objective**: To create a community-driven ecosystem for strategy sharing

- 🔄 **Strategy Marketplace**: Listings API with Stripe Connect integration
- 🔄 **Copy Trading**: Subscription-based strategy following
- 🔄 **Community Features**: Strategy ratings, reviews, and social features

## 📊 Project Metrics (December 2025)

- **Lines of Code**: 25,000+ (Python, JavaScript, TypeScript)
- **Number of Services**: 22 microservices
- **Number of Commits**: 200+
- **Number of Tests**: 150+ test files
- **Contributors**: 3+ active developers

## 📊 2025 Review & Next Steps

A complete technical review of the repository was conducted in November 2025. The project has evolved significantly with the addition of visual strategy creation tools, AI assistance, and comprehensive monitoring capabilities.

- **Key achievements**: Visual Strategy Designer, AI-powered strategy generation, comprehensive dashboard, multi-channel notifications
- **Current focus**: Marketplace beta launch, advanced analytics, community features
- **Next priorities**: Mobile app, advanced risk management, institutional features

Find the detailed review, roadmap and backlog in:

- [`docs/reports/2025-11-code-review.md`](docs/reports/2025-11-code-review.md)
- [`docs/project-evaluation.md`](docs/project-evaluation.md)
- [`docs/tasks/2025-q4-backlog.md`](docs/tasks/2025-q4-backlog.md)
- [`docs/release-highlights/2025-12.md`](docs/release-highlights/2025-12.md)

## 🗺️ Roadmap and Next Steps

### Short-term Priorities (0-3 months)

1. **Marketplace Launch**
   - Complete Stripe Connect integration
   - Launch beta marketplace with selected strategy creators
   - Implement copy trading subscriptions

2. **Advanced Analytics**
   - Enhanced risk metrics and portfolio analytics
   - Performance attribution analysis
   - Advanced backtesting features

3. **Mobile Experience**
   - Responsive web design improvements
   - Progressive Web App (PWA) features
   - Mobile-optimized trading interface

### Medium-term Goals (3-6 months)

1. **Institutional Features**
   - Multi-user accounts and permissions
   - Advanced compliance and reporting
   - Institutional-grade risk management

2. **Advanced AI Features**
   - Strategy optimization recommendations
   - Market regime detection
   - Automated risk adjustment

3. **Ecosystem Expansion**
   - Additional exchange integrations
   - Third-party plugin system
   - API marketplace for developers

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

## 📞 Support and Community

- **GitHub Issues**: To report bugs or suggest features
- **Discussions**: To interact with the community
- **Documentation**: Complete guide in the `docs/` folder

## 📄 License

This project is licensed under the MIT License - see the `LICENSE` file for more details.

---

> **Developed with ❤️ by decarvalhoe and the open-source community**
> Last updated: December 2025
