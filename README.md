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
- ✅ **Development Environment**: Docker, database, services
- ✅ **Configuration Service**: Centralized parameter management

*Result*: The technical infrastructure is operational and ready for development.

### Phase 2: Authentication and Users (🔄 In Progress)
**Objective**: To allow users to create accounts and log in securely

- 🔄 **Authentication System**: Registration, login, JWT security
- 🔄 **Profile Management**: Creation and modification of user profiles
- 🔄 **Database**: Structure to store user information

*Expected Result*: Users will be able to create secure accounts and manage their profiles.

### Phase 3: Trading Strategies (📋 Planned)
**Objective**: To allow the creation and execution of trading strategies

- 📋 **Strategy Engine**: Creation and configuration of custom strategies
- 📋 **Market Connectors**: Integration with trading platforms
- 📋 **Order Management**: Placement and tracking of automated orders

### Phase 4: Monitoring and Analytics (📋 Planned)
**Objective**: To provide tools for performance analysis and tracking

- 📋 **Dashboards**: Real-time performance visualization
- 📋 **Alerts and Notifications**: Customizable alert system
- 📋 **Detailed Reports**: In-depth analysis of results

## 🛠️ For Developers

### Quick Start

```bash
# 1. Clone the project
git clone https://github.com/decarvalhoe/trading-bot-open-source.git
cd trading-bot-open-source

# 2. Install development tools
make setup

# 3. Start the development environment
make dev-up

# 4. Check that everything is working
curl http://localhost:8000/health

# 5. Stop the environment
make dev-down
```

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

A complete technical review of the repository was conducted in September 2025. It confirms the strength of the current architecture (FastAPI microservices, shared entitlements middleware) and highlights the priority initiatives needed to deliver an operational trading journey.

- **Key strengths**: advanced authentication foundation (TOTP MFA, roles), E2E CI, onboarding-friendly Makefile, structured documentation.
- **Watch points**: trading services still nascent, limited test coverage, lack of observability and security governance.
- **Recommended priorities (0-3 months)**: finalize `user-service`, scope the trading MVP, expand testing (unit + TOTP E2E), introduce observability and secure secret management.

Find the detailed report and mid-term roadmap in [`docs/project-evaluation.md`](docs/project-evaluation.md).

## 📞 Support and Community

- **GitHub Issues**: To report bugs or suggest features
- **Discussions**: To interact with the community
- **Documentation**: Complete guide in the `docs/` folder

## 📄 License

This project is licensed under the MIT License - see the `LICENSE` file for more details.

---

> **Developed with ❤️ by decarvalhoe and the open-source community**
> Last updated: September 2025
