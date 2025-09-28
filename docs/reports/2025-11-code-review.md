# Rapport de revue de code — Novembre 2025

## 1. Périmètre de la revue

Cette revue couvre l'état du dépôt `trading-bot-open-source` au 25 novembre 2025. Elle s'appuie sur
l'analyse des principaux services Python (FastAPI), des bibliothèques partagées sous `libs/`,
des fournisseurs `providers/` ainsi que des actifs d'infrastructure (`docker-compose`, observabilité).
Les constats sont regroupés par domaine afin d'orienter les prochaines itérations produit et
techniques.

## 2. Architecture applicative

- **Services Auth & Utilisateurs** — `auth-service` expose l'inscription, la connexion, la MFA TOTP et la
gestion des rôles via SQLAlchemy, tandis que `user-service` fournit un CRUD complet sur le profil et les
préférences avec masquage des champs sensibles pour les tiers.【F:services/auth-service/app/main.py†L1-L88】【F:services/user-service/app/main.py†L1-L132】
- **Stratégies & Exécution** — `algo-engine` maintient un catalogue en mémoire avec orchestrateur,
backtester et import déclaratif de stratégies; `order-router` combine adaptateurs brokers, moteur de
risque (limites dynamiques, stop-loss, alertes) et suivi des exécutions en mémoire.【F:services/algo-engine/app/main.py†L1-L136】【F:services/order-router/app/main.py†L1-L143】
- **Données de marché** — `market_data` expose des webhooks TradingView, des snapshots de quotes/orderbook
et configure les adaptateurs Binance/IBKR via des limites sandbox mutualisées.【F:services/market_data/app/main.py†L1-L88】【F:providers/limits.py†L1-L120】
- **Librairies transverses** — l'entitlements middleware unifie les contrôles d'accès, `libs/observability`
ofre logs structurés (correlation/request id) et métriques Prometheus, `libs/secrets` centralise la
résolution de secrets multi-providers.【F:libs/entitlements/__init__.py†L1-L34】【F:libs/observability/logging.py†L1-L123】【F:libs/observability/metrics.py†L1-L80】【F:libs/secrets/__init__.py†L1-L120】

## 3. Qualité, tests et outillage

- **Tests unitaires** — `user-service` possède une suite couvrant le parcours inscription → activation →
profil, y compris l'application des entitlements; d'autres services n'ont pas encore de tests dédiés.
【F:services/user-service/tests/test_user.py†L1-L128】
- **Tests E2E & CI** — des scripts Bash/Powershell valident le flux auth dans la CI GitHub Actions, et le
Makefile automatise lint/tests/coverage pour un onboarding rapide.【F:codex.plan.yaml†L45-L109】【F:Makefile†L1-L28】
- **Observabilité & monitoring** — toutes les APIs FastAPI installent le middleware de logs structurés et
exposent `/metrics`; `docker-compose` embarque Prometheus+Grafana pré-configurés pour la collecte locale.
【F:services/auth-service/app/main.py†L12-L24】【F:services/user-service/app/main.py†L25-L52】【F:docker-compose.yml†L1-L56】

## 4. Points forts constatés

1. **Couche sécurité mature** — authentification robuste (TOTP, rôles, quotas), entitlements uniformisés,
   secrets externalisables.
2. **Base trading cohérente** — limites sandbox partagées, moteur d'orchestration, moteur de risque riche
   (stop-loss, limites dynamiques) offrent un socle MVP crédible.
3. **Observabilité intégrée** — logs JSON corrélés, métriques, stack Prometheus/Grafana prête à l'emploi,
   facilitant le futur déploiement.

## 5. Axes d'amélioration

1. **Persistance et scalabilité** — `algo-engine` et `order-router` fonctionnent en mémoire; il faut
   prévoir la persistance (DB ou cache distribué) pour passer en production.【F:services/algo-engine/app/main.py†L27-L74】【F:services/order-router/app/main.py†L33-L111】
2. **Tests multi-services** — absence de tests contractuels pour `market_data`, `order-router`,
   `algo-engine`; à combler avant d'ouvrir les contributions externes.
3. **Sécurité opérationnelle** — le gestionnaire de secrets est prêt mais nécessite documentation
   d'intégration (Vault/Doppler/AWS) et procédures de rotation effectives.
4. **Parcours utilisateurs** — aligner `auth-service` et `user-service` dans des scénarios E2E end-to-end
   (inscription ➜ activation ➜ profil ➜ TOTP) pour fiabiliser l'expérience.

## 6. Recommandations prioritaires (0-3 mois)

1. **Finaliser le MVP parcours utilisateur** : orchestrer auth + user-service dans les tests E2E,
   documenter l'OpenAPI et ajouter un guide front pour les appels critiques.
2. **Solidifier le trading sandbox** : persister les stratégies, enregistrer les exécutions, exposer une
   CLI démonstration s'appuyant sur `providers/limits` pour dérouler un trade complet.
3. **Industrialiser l'observabilité** : publier un playbook Prometheus/Grafana, brancher l'alerte latence
   > 1s ou taux 5xx > 2% et définir l'escalade.
4. **Sécuriser les secrets** : documenter les recettes Vault/Doppler/AWS, ajouter des checks de cohérence
   dans la CI (lint des manifestes secrets) et définir une fréquence de rotation.

## 7. Feuille de route moyen terme (3-9 mois)

- **Gestion des risques avancée** : enrichir le moteur de règles (verrouillage progressif, gestion multi-comptes)
  et produire un reporting quotidien automatisé.
- **Connecteurs marchés réels** : isoler des tests d'intégration par broker avec mocks contrôlés et gérer
  le rate limiting via `AsyncRateLimiter`.
- **Interface utilisateur minimale** : étendre `web-dashboard` ou un front léger affichant portefeuille,
  exécutions, alertes.
- **Gouvernance open-source** : maintenir un changelog actif, publier un backlog public aligné sur la
  roadmap trimestrielle, formaliser la checklist de revue sécurité dans `CONTRIBUTING.md`.

## 8. Actions documentaires

- Mettre à jour la roadmap trimestrielle (2025-2026) avec jalons MVP trading & observabilité.
- Publier cette revue et le backlog associé (`docs/tasks/2025-q4-backlog.md`).
- Rafraîchir les README (EN/FR) avec les dernières avancées et pointer vers ce rapport.
