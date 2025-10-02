# Order Router Service

Le service **Order Router** centralise l'envoi d'ordres vers plusieurs brokers et applique des règles de risque.

## Adaptateurs broker

Deux adaptateurs sont fournis :

- `BinanceAdapter` : confirmation immédiate et exécution pleine.
- `IBKRAdapter` : simulateur d'Interactive Brokers avec remplissage partiel.

Chaque adaptateur hérite de `BrokerAdapter` et implémente `place_order`.

## Règles de risque

Le module `risk_rules.py` expose :

- `MaxNotionalRule` : plafond de notionnel par symbole.
- `MaxDailyLossRule` : stop-loss journalier agrégé.
- `RiskEngine` : applique séquentiellement les règles.

## API principale

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/health` | Statut du service |
| GET | `/brokers` | Liste des brokers disponibles |
| POST | `/orders` | Routage d'un ordre après validation du risque |
| POST | `/orders/{broker}/cancel` | Annulation d'un ordre |
| GET | `/orders/log` | Journal des ordres soumis (filtres par compte, symbole, date, tag, stratégie) |
| POST | `/orders/{id}/notes` | Ajout d'une note et de tags manuels sur un ordre |
| GET | `/executions` | Exécutions agrégées |
| GET | `/state` | Etat (mode paper/live, consommation de notionnel) |
| PUT | `/state` | Mise à jour du mode et de la limite journalière |

Le middleware d'entitlements applique la capacité `can.route_orders`. L'état interne empêche de dépasser la limite de notionnel routé.

## Exemple d'ordre

```bash
curl -X POST http://localhost:8100/orders \
  -H 'Content-Type: application/json' \
  -d '{
        "broker": "binance",
        "symbol": "BTCUSDT",
        "quantity": 0.5,
        "price": 30000
      }'
```
