# Évaluation du projet Trading Bot Open Source

_Date de l'évaluation : novembre 2025_

## 1. Résumé exécutif

Le projet **Trading Bot Open Source** consolide une architecture microservices moderne (FastAPI,
SQLAlchemy) avec des briques de sécurité et d'observabilité déjà intégrées. Les fondations
utilisateur (authentification, profils) sont opérationnelles et le socle trading (algo-engine,
order-router, market-data) dispose d'un premier jeu de limites sandbox. Les prochaines itérations
portent sur la persistance des stratégies, l'industrialisation des tests contractuels et la
formalisation des procédures de gestion des secrets.

## 2. Architecture et code

- **Services d'identité** : `auth-service` gère l'inscription, la connexion JWT, la MFA TOTP et les rôles,
  tandis que `user-service` fournit le CRUD complet sur les profils avec masquage des champs sensibles
  selon les entitlements.【F:services/auth-service/app/main.py†L1-L88】【F:services/user-service/app/main.py†L1-L132】
- **Moteur de stratégies** : `algo-engine` expose un catalogue in-memory avec orchestrateur, backtester et
  import YAML/Python; les stratégies sont enregistrées via une API FastAPI dédiée.【F:services/algo-engine/app/main.py†L1-L136】
- **Routage d'ordres** : `order-router` combine adaptateurs Binance/IBKR simulés, moteur de risque (limites
  dynamiques, stop-loss, notional max) et journal en mémoire des exécutions.【F:services/order-router/app/main.py†L1-L143】
- **Données de marché** : `market_data` fournit un webhook TradingView sécurisé (HMAC), expose quotes et
  orderbooks basés sur les limites sandbox partagées dans `providers/limits.py`.【F:services/market_data/app/main.py†L1-L88】【F:providers/limits.py†L1-L120】
- **Libs transverses** : entitlements middleware mutualisé, logs JSON corrélés, métriques Prometheus et
  gestionnaire de secrets multi-providers sont disponibles pour tous les services.【F:libs/entitlements/__init__.py†L1-L34】【F:libs/observability/logging.py†L1-L123】【F:libs/observability/metrics.py†L1-L80】【F:libs/secrets/__init__.py†L1-L120】

## 3. Infrastructure et opérations

- **Conteneurisation** : `docker-compose` orchestre Postgres, Redis, auth/user services et ajoute la stack
  Prometheus/Grafana pré-configurée pour le monitoring local.【F:docker-compose.yml†L1-L56】
- **Outillage** : le `Makefile` centralise setup, lint, tests, coverage et lancement de la stack locale, ce
  qui facilite l'onboarding des contributeurs.【F:Makefile†L1-L28】
- **Observabilité** : toutes les APIs installent le middleware de logs structurés et exposent `/metrics`,
  permettant la collecte par Prometheus dès le démarrage.【F:services/auth-service/app/main.py†L12-L24】【F:services/user-service/app/main.py†L25-L52】

## 4. Tests et qualité

- **Unitaires** : `user-service` dispose d'une suite couvrant le parcours complet (inscription, activation,
  préférences, masquage entitlements).【F:services/user-service/tests/test_user.py†L1-L128】
- **E2E** : des scripts Bash/PowerShell exécutent le flux auth (register/login/me) et sont intégrés à la CI
  GitHub Actions via `codex.plan.yaml` (workflow `e2e`).【F:codex.plan.yaml†L45-L109】
- **Qualité** : la configuration `pyproject.toml` impose Black, isort, Flake8, Mypy strict, garantissant un
  socle cohérent pour de futures contributions.【F:pyproject.toml†L1-L35】

## 5. Documentation et communauté

- **Guides** : README (EN/FR) détaillent l'architecture, les phases projet et l'onboarding. Les guides
  complémentaires (`docs/`) couvrent stratégies, observabilité, sécurité, governance et roadmap.【F:README.md†L1-L120】【F:docs/ROADMAP.md†L1-L24】
- **Gouvernance** : le comité KPI hebdomadaire est documenté (`docs/governance/kpi-review.md`) et la roadmap
  2025→2026 aligne releases et backlog (`docs/tasks/2025-q4-backlog.md`).【F:docs/governance/kpi-review.md†L1-L40】【F:docs/tasks/2025-q4-backlog.md†L1-L56】

## 6. Risques et points d'attention

1. **Persistance manquante** : `algo-engine` et `order-router` conservent l'état en mémoire, limitant la
   scalabilité et la résilience. Prioriser l'externalisation vers Postgres/Redis.【F:services/algo-engine/app/main.py†L27-L74】【F:services/order-router/app/main.py†L33-L111】
2. **Couverture tests hétérogène** : seuls auth/user disposent de tests solides; `market_data`,
   `order-router`, `algo-engine` nécessitent des tests contractuels et unitaires additionnels.
3. **Secrets & conformité** : le gestionnaire de secrets n'est pas encore accompagné de procédures
   d'exploitation (Vault/Doppler/AWS), augmentant le risque opérationnel.【F:libs/secrets/__init__.py†L1-L120】
4. **Experience utilisateur** : l'enchaînement auth ➜ profil ➜ TOTP n'est pas documenté via un parcours
   complet (E2E ou guide), ce qui peut ralentir l'adoption.

## 7. Recommandations court terme (0-3 mois)

1. **Aligner les scénarios E2E** : fusionner les scripts auth et user-service, couvrir les cas d'erreur et
   publier une documentation API front-friendly.
2. **Persister l'état trading** : introduire des dépôts (SQL/Redis) pour les stratégies et journaux
   d'ordres, ajouter les migrations nécessaires et mettre à jour les docs.
3. **Playbook observabilité** : documenter l'utilisation de Prometheus/Grafana, configurer une alerte
   latence/taux d'erreur et intégrer ces checks à la CI/CD.
4. **Industrialiser les secrets** : fournir des guides pas-à-pas pour Vault, Doppler et AWS Secrets Manager,
   ajouter des validations automatiques dans la CI.

## 8. Roadmap moyen terme (3-9 mois)

- **Trading sandbox avancé** : enrichir le backtesting, exposer un reporting P&L quotidien et intégrer le
  moteur de règles de risque aux connecteurs live.
- **Connecteurs marchés** : prioriser Binance/IBKR, ajouter des tests d'intégration et documenter la gestion
  du rate limiting via `AsyncRateLimiter`.
- **Expérience utilisateur** : livrer une première page `web-dashboard` listant positions/ordres et intégrer
  des notifications critiques (webhooks, email, Slack).
- **Gouvernance** : maintenir un changelog actif, publier un backlog GitHub Projects synchronisé avec la
  roadmap trimestrielle et formaliser la checklist sécurité dans `CONTRIBUTING.md`.

## 9. Indicateurs de succès

| Indicateur | Cible | Horizon | Notes |
| --- | --- | --- | --- |
| Taux de réussite E2E (auth + user) | > 95 % | Continu | Bloquer les merges si la pipeline échoue. |
| Couverture tests services critiques | ≥ 60 % | Juin 2026 | Priorité sur auth, user, algo, order-router, market-data. |
| Temps d'onboarding dev | < 1 journée | Continu | Garder README/Makefile à jour et mesurer via sondages. |
| Stratégie sandbox démontrable | 1 parcours complet | Mars 2026 | Script CLI et rapport de performance publiés. |
| Contributeurs externes actifs | ≥ 5 PR/trim | 2026 | Appuyer la gouvernance communautaire et la roadmap publique. |

---

Pour la synthèse détaillée et le backlog priorisé, consulter :
- Rapport de revue : `docs/reports/2025-11-code-review.md`.
- Backlog : `docs/tasks/2025-q4-backlog.md`.
