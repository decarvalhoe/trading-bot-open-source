# Parcours MVP en environnement sandbox

Ce guide décrit le flux cible entre les services `market_data`, `algo-engine` et `order-router`
pour une exécution spot simplifiée. Il s'appuie sur les nouveaux contrats de données partagés
(`schemas/market.py`) et sur les limites configurées dans `providers/limits.py`.

## Politique de retry du client order-router

Le client asynchrone `OrderRouterClient` applique désormais une stratégie de retry
exponentiel pour sécuriser l'appel `POST /orders` :

- jusqu'à trois tentatives sur les erreurs réseau (`httpx.HTTPError`) ou les réponses 5xx,
- des délais d'attente de 0,5 s, 1 s puis 2 s entre chaque tentative,
- journalisation de chaque tentative échouée pour faciliter l'observabilité.

Au-delà de ces trois essais ou en cas d'erreur fonctionnelle (4xx), le client renvoie une
erreur `OrderRouterClientError` afin que l'orchestrateur puisse placer la stratégie en état
`ERROR` et déclencher les alertes correspondantes.

## Endpoints exposés

| Service | Endpoint | Description |
| --- | --- | --- |
| `market_data` | `GET /spot/{symbol}?venue=binance.spot` | Retourne un `Quote` synthétique (bid/ask/mid) pour le symbole demandé. |
| `market_data` | `GET /orderbook/{symbol}?venue=binance.spot` | Fournit un `OrderBookSnapshot` cohérent avec les limites sandbox. |
| `algo-engine` | `POST /mvp/plan` | Construit un `ExecutionPlan` prêt à être routé (quote + book + ordre). |
| `order-router` | `POST /plans` | Génère la même vue côté routing en s'appuyant sur les règles de risque. |
| `order-router` | `POST /orders` | Route l'ordre standardisé et renvoie un `ExecutionReport`. |
| `order-router` | `GET /orders/log` / `GET /executions` | Suivi des reconnaissances et des remplissages en format partagé. |

## Script CLI `scripts/dev/bootstrap_demo.py`

Le script `bootstrap_demo.py` enchaîne désormais les appels HTTP vers la stack (assurez-vous d'avoir exécuté `pip install -r services/algo-engine/requirements.txt` si vous souhaitez tester l'assistant IA)
docker locale pour provisionner un utilisateur, activer son profil, configurer
une stratégie, router un ordre, générer un rapport, créer une alerte et publier
un événement de streaming. Il prépare automatiquement les entitlements via le
`billing-service` (plan + souscriptions) sauf si l'option `--skip-billing-setup`
est spécifiée.

```bash
$ scripts/dev/bootstrap_demo.py BTCUSDT 0.5 --order-type market \
    --auth-url http://127.0.0.1:8011 --user-url http://127.0.0.1:8012
```

La sortie JSON récapitule les identifiants utiles (utilisateur, stratégie,
ordre, alerte, chemin du rapport, réponse streaming) ainsi que les tokens
d'authentification générés pour le compte de démonstration. Le script
`run_mvp_flow.py` agit comme un simple wrapper et délègue directement à ce
nouveau flux bootstrap.
