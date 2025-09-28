# Codex Automation Platform

Le projet Codex automatise les interactions GitHub/Stripe/TradingView pour gérer le cycle de vie des contributions ouvertes et la facturation associée.

## Architecture

- **Gateway** (`services/codex_gateway/`, service "codex-gateway") : service FastAPI exposant les webhooks `/webhooks/github`, `/webhooks/stripe` et `/webhooks/tradingview`. Les signatures HMAC des fournisseurs sont vérifiées avant la mise en file des événements dans le broker mémoire.
- **Worker** (`services/codex_worker/`, service "codex-worker") : consomme les événements, pilote les Checks GitHub, exécute les plans/pytest dans des conteneurs jetables et vérifie les droits via OpenFeature.
- **Librairie partagée** (`libs/codex/`) : modèles d'événements et broker mémoire permettant les tests unitaires et un usage local.

## Commandes supportées

Les commandes s'exécutent via des commentaires GitHub sur les Pull Requests :

| Commande | Description |
| --- | --- |
| `/codex plan` | Crée un check-run, clone le dépôt dans un conteneur (image `ghcr.io/trading-bot/codex-sandbox:latest`), installe les dépendances dev et lance `pytest`. Le résultat est commenté dans la PR avec les logs. |
| `/codex pr` | Déclenche le workflow de merge automatique (`merge_method = squash`) après validation des entitlements. |

Chaque commande nécessite une capability OpenFeature : `codex.plan` ou `codex.pr`. Les attributs utilisés sont `user` (auteur du commentaire) et `repository`.

## Gouvernance des branches

- Les branches `main` et `release/*` sont protégées et ne peuvent être modifiées que par le workflow `/codex pr` après validation.
- Les branches de fonctionnalités doivent suivre le préfixe `feature/<ticket>`.
- Les merges effectués par le worker utilisent systématiquement `merge_method=squash` afin de garantir un historique linéaire.

## Configuration du GitHub App

1. Créer une GitHub App avec les permissions suivantes :
   - Checks : `Read & write`
   - Pull requests : `Read & write`
   - Issues : `Read & write`
   - Repository contents : `Read`
   - Webhooks : URL `https://<gateway>/webhooks/github`, secret `CODEX_GATEWAY_GITHUB_WEBHOOK_SECRET`
2. Installer l'application sur les dépôts cibles et récupérer le token d'installation (stocké dans `CODEX_WORKER_GITHUB_TOKEN`).
3. Définir les événements webhook obligatoires : `issue_comment`, `pull_request`, `check_suite`.

## Workflows GitHub Actions

Trois workflows réutilisables sont fournis :

- `.github/workflows/lint.yml` : exécute `make lint` sur un environnement Python 3.12.
- `.github/workflows/test.yml` : installe `requirements-dev.txt`, lance `make test` et publie les rapports pytest.
- `.github/workflows/codex-run.yml` : workflow déclenché par commentaire `/codex <cmd>` qui appelle le worker via un job réutilisable.

Les workflows sont définis avec `workflow_call` pour être invoqués depuis les pipelines de produit.

## Secrets et déploiement

Les environnements GitHub Actions doivent définir les secrets suivants :

| Secret | Service | Description |
| --- | --- | --- |
| `CODEX_GATEWAY_GITHUB_WEBHOOK_SECRET` | Gateway | Signature HMAC GitHub. |
| `CODEX_GATEWAY_STRIPE_WEBHOOK_SECRET` | Gateway | Signature Stripe. |
| `CODEX_GATEWAY_TRADINGVIEW_WEBHOOK_SECRET` | Gateway | Signature TradingView. |
| `CODEX_WORKER_GITHUB_TOKEN` | Worker | Token d'installation de la GitHub App. |
| `CODEX_WORKER_SANDBOX_IMAGE` | Worker | (Optionnel) Image alternative pour le conteneur sandbox. |
| `CODEX_OPENFEATURE_PROVIDER` | Worker | (Optionnel) Configuration du provider OpenFeature en production. |

Pour un déploiement sur Kubernetes, les secrets peuvent être provisionnés via `infra/` (Terraform/Helm) et injectés dans les pods `codex-gateway` et `codex-worker`. Les workflows GitHub Actions peuvent utiliser `environment` + `secrets` afin de synchroniser la configuration avec les environnements de staging/production.
