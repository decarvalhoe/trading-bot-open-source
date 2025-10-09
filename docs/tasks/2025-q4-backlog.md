# Backlog priorisé — Q4 2025

Cette liste couvre les chantiers techniques prioritaires issus de la revue de novembre 2025.
Les tâches sont regroupées par criticité et se réfèrent aux services et bibliothèques existants.

## 🔴 Criticité élevée

1. **Boucler le parcours utilisateur et l'OpenAPI**
   - Aligner `auth-service` et `user-service` dans un scénario E2E unique incluant TOTP (inscription ➜ activation ➜ profil ➜ MFA).【F:services/auth-service/app/main.py†L1-L88】【F:services/user-service/tests/test_user.py†L1-L128】
   - Générer et publier la documentation OpenAPI consolidée (`docs/api/user-auth.md`) avec exemples de requêtes front.
   - Ajouter des tests de régression pour les statuts d'erreur 4xx (email en doublon, TOTP invalide).

2. **Durcir la persistance trading**
   - Industrialiser les migrations Alembic pour `algo-engine` et `order-router`, tests de rollback inclus.【F:services/algo_engine/app/repository.py†L46-L96】【F:services/order_router/app/main.py†L1702-L1775】
   - Instrumenter les sessions SQLAlchemy (logs, métriques Prometheus) et documenter les procédures de reprise.
   - Ajouter un plan de purge/archivage pour les stratégies et journaux d'ordres (rotation, rétention).

3. **Renforcer la gestion des secrets**
   - Documenter les procédures Vault/Doppler/AWS en s'appuyant sur `libs/secrets` et fournir des manifests d'exemple.【F:libs/secrets/__init__.py†L1-L120】
   - Introduire des checks CI validant la présence des variables critiques (JWT, API keys).
   - Ajouter une checklist de rotation dans `CONTRIBUTING.md`.

4. **Tests contractuels multi-services**
   - Créer des suites Schemathesis/Pydantic pour `market_data` et compléter `algo-engine`/`order-router` avec des scénarios persistance + risques.【F:services/market_data/app/main.py†L1-L88】【F:services/order_router/tests/test_order_router.py†L1-L256】【F:services/algo_engine/tests/test_backtests.py†L1-L184】
   - Intégrer ces suites dans la CI (workflow dédié) et publier les rapports associés.

## 🟠 Criticité moyenne

1. **Démo trading sandbox**
   - Livrer un script CLI (`scripts/dev/demo_trade.py`) orchestrant quote ➜ plan ➜ ordre ➜ rapport via les services existants.【F:providers/limits.py†L1-L120】
   - Documenter le parcours dans `docs/mvp-sandbox-flow.md`.

2. **Playbook observabilité**
   - Décrire le déploiement Prometheus/Grafana local & cloud, y compris l'alerte latence/erreur.【F:docker-compose.yml†L1-L56】
   - Ajouter un tableau de bord Grafana partagé (`docs/observability/dashboards/roadmap.json`).

3. **Connecteurs marchés**
   - Prioriser Binance Spot : ajouter des tests d'intégration avec `AsyncRateLimiter` et gestion d'erreurs API.【F:services/market_data/adapters/__init__.py†L1-L11】
   - Définir un plan de certification pour IBKR (mocks, sandbox IBKR).

4. **Documentation développeur**
   - Mettre à jour `README`/`README.fr` avec les nouveaux ports (`8011`, `8012`) et pointer vers le rapport de revue.【F:README.md†L1-L120】【F:README.fr.md†L1-L120】
   - Ajouter un guide "première PR" détaillé dans `CONTRIBUTING.md`.

## 🟡 Criticité faible

1. **Gouvernance & communauté**
   - Publier un backlog public (GitHub Projects) aligné sur cette liste et synchroniser la roadmap trimestrielle.【F:docs/ROADMAP.md†L1-L40】
   - Documenter un rituel communautaire (AMA trimestriel) dans `docs/community`.

2. **Reporting & KPI**
   - Relier le tableau de bord KPI (`docs/metrics`) aux nouveaux tests/alertes.
   - Automatiser la génération d'un rapport mensuel (coverage, E2E, incidents).

3. **Expérience utilisateur**
   - Étendre `web-dashboard` avec une page statique affichant les derniers ordres simulés.
   - Préparer un kit design minimal (`docs/ui/style-guide.md`).
