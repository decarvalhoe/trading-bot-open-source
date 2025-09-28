# Parcours MVP en environnement sandbox

Ce guide décrit le flux cible entre les services `market_data`, `algo-engine` et `order-router`
pour une exécution spot simplifiée. Il s'appuie sur les nouveaux contrats de données partagés
(`schemas/market.py`) et sur les limites configurées dans `providers/limits.py`.

## Endpoints exposés

| Service | Endpoint | Description |
| --- | --- | --- |
| `market_data` | `GET /spot/{symbol}?venue=binance.spot` | Retourne un `Quote` synthétique (bid/ask/mid) pour le symbole demandé. |
| `market_data` | `GET /orderbook/{symbol}?venue=binance.spot` | Fournit un `OrderBookSnapshot` cohérent avec les limites sandbox. |
| `algo-engine` | `POST /mvp/plan` | Construit un `ExecutionPlan` prêt à être routé (quote + book + ordre). |
| `order-router` | `POST /plans` | Génère la même vue côté routing en s'appuyant sur les règles de risque. |
| `order-router` | `POST /orders` | Route l'ordre standardisé et renvoie un `ExecutionReport`. |
| `order-router` | `GET /orders/log` / `GET /executions` | Suivi des reconnaissances et des remplissages en format partagé. |

## Script CLI `scripts/dev/run_mvp_flow.py`

Le script Python `run_mvp_flow.py` orchestre ce parcours sans dépendre de services
réels : il consomme la configuration sandbox, construit un `OrderRequest` puis
un `ExecutionPlan`, et affiche la structure complète en JSON.

```bash
$ scripts/dev/run_mvp_flow.py BTCUSDT 0.5 --side buy --price 30000
```

La sortie contient :

- la définition normalisée de l'ordre (`order`),
- le `Quote` et l'`OrderBookSnapshot` synthétiques,
- la structure `plan` utilisée par les services,
- les limites associées à la paire (quantité max, fréquence de rafraîchissement, etc.).

Ce script constitue une démonstration reproductible du flux MVP : les mêmes
structures sont utilisées par les endpoints REST correspondants, garantissant
l'alignement contractuel entre les services.
