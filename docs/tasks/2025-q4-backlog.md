# Backlog priorisé — Q4 2025

Cette liste couvre les chantiers techniques prioritaires issus de la revue de novembre 2025.
Les tâches sont regroupées par criticité et se réfèrent aux services et bibliothèques existants.

## 🔴 Criticité élevée

1. **Boucler le parcours utilisateur et l'OpenAPI**
   - Aligner `auth-service` et `user-service` dans un scénario E2E unique incluant TOTP (inscription ➜ activation ➜ profil ➜ MFA).【F:services/auth-service/app/main.py†L1-L88】【F:services/user-service/tests/test_user.py†L1-L128】
   - Générer et publier la documentation OpenAPI consolidée (`docs/api/user-auth.md`) avec exemples de requêtes front.
   - Ajouter des tests de régression pour les statuts d'erreur 4xx (email en doublon, TOTP invalide).

2. **Persister les stratégies et exécutions**
   - Externaliser `StrategyStore` et `OrderRouter` vers une base PostgreSQL/Redis afin de lever la limite in-memory.【F:services/algo-engine/app/main.py†L27-L74】【F:services/order-router/app/main.py†L33-L111】
   - Documenter le schéma de persistance (`docs/algo-engine.md`, `docs/order-router.md`).
   - Ajouter des migrations infra correspondantes.

3. **Renforcer la gestion des secrets**
   - Documenter les procédures Vault/Doppler/AWS en s'appuyant sur `libs/secrets` et fournir des manifests d'exemple.【F:libs/secrets/__init__.py†L1-L120】
   - Introduire des checks CI validant la présence des variables critiques (JWT, API keys).
   - Ajouter une checklist de rotation dans `CONTRIBUTING.md`.

4. **Tests contractuels multi-services**
   - Créer des suites Schemathesis/Pydantic pour `market_data`, `order-router`, `algo-engine` (health, erreurs).【F:services/market_data/app/main.py†L1-L88】【F:services/order-router/app/main.py†L1-L143】【F:services/algo-engine/app/main.py†L1-L136】
   - Intégrer ces suites dans la CI (workflow dédié).

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
