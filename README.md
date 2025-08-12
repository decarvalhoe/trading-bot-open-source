# Trading Bot Open Source — Sprint 1 Pack

**Phase 1 / Sprint 1** — Infrastructure & Fondations (TICKET-001 à TICKET-003).

## TL;DR (dev)

```bash
# 0) (optionnel) activer pre-commit localement
pipx install pre-commit || pip install pre-commit
pre-commit install

# 1) Lancer l'env de dev
make dev-up

# 2) Vérifier le service de configuration
curl http://localhost:8000/health
curl http://localhost:8000/config/current

# 3) Arrêter
make dev-down
```

## Architecture (Sprint 1)
- `services/config-service` : Service FastAPI pour **configuration centralisée** (validation Pydantic, env par environnement, API REST).
- `infra` : Docker Compose (PostgreSQL, Redis, RabbitMQ).

## Décisions
- **Python 3.12**. FastAPI + Pydantic Settings.
- **Docker multi-stage** et `docker-compose.yml` pour le dev local.
- **CI GitHub Actions** (lint + tests).
- **pre-commit** : black, isort, flake8, mypy, bandit, detect-secrets.

## Prochaines étapes (Sprint 1)
- TICKET-001 : Repo + templates + CI minimal ✅ (inclus ici).
- TICKET-002 : Environnement Docker + Compose ✅ (inclus ici).
- TICKET-003 : Config-service avec Pydantic + API ✅ (MVP ici, extensible DB plus tard).

---

> Auteur: Manus AI — Date: 20 janvier 2025 — Version: 1.0
