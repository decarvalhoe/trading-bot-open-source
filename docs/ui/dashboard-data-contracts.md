# Contrats JSON du tableau de bord

Ce document décrit la structure des données échangées entre le service **web-dashboard** et les
systèmes amont. Il sert de référence pour la mise en cache du contexte initial `/dashboard` et pour
les messages temps réel transmis via le service de streaming.

## Contexte initial `/dashboard`

L'endpoint `/dashboard` rend une page HTML qui embarque un objet `context` sérialisé en JSON.
Les propriétés suivantes sont exposées en plus des portefeuilles, transactions, alertes et métriques
historiquement disponibles :

```jsonc
{
  "strategies": [
    {
      "id": "92a939a2-57d5-4df3-a6c7-9d0b15efc2a4",
      "name": "Static",
      "status": "ACTIVE",           // Valeurs possibles : PENDING, ACTIVE, ERROR
      "enabled": true,
      "strategy_type": "static",     // Identifiant du plugin orchestrateur
      "tags": ["intraday"],
      "last_error": null,
      "last_execution": {
        "order_id": "order-success",
        "status": "FILLED",
        "submitted_at": "2024-02-01T09:15:22.581729Z",
        "symbol": "BTCUSDT",
        "venue": "BINANCE_SPOT",
        "side": "BUY",
        "quantity": 1.0,
        "filled_quantity": 1.0
      },
      "metadata": {
        "strategy_id": "92a939a2-57d5-4df3-a6c7-9d0b15efc2a4"
      }
    }
  ],
  "logs": [
    {
      "timestamp": "2024-02-01T09:15:22.581729Z",
      "level": "info",
      "message": "FILLED BTCUSDT (ordre order-success)",
      "order_id": "order-success",
      "status": "FILLED",
      "symbol": "BTCUSDT",
      "strategy_id": "92a939a2-57d5-4df3-a6c7-9d0b15efc2a4",
      "strategy_hint": "static",
      "extra": {
        "broker": "paper",
        "side": "BUY"
      }
    }
  ]
}
```

### Règles de construction

- Le tableau `strategies` est alimenté par l'API de l'orchestrateur (`GET /strategies`).
  - `status` reprend l'état courant (`PENDING`, `ACTIVE`, `ERROR`).
  - `last_execution` est calculée à partir de l'historique `recent_executions` retourné par
    l'orchestrateur. Les correspondances se basent sur l'`id`, les métadonnées ou les tags `strategy:`.
- Les éléments du tableau `logs` sont des instances normalisées de `recent_executions`.
  - `timestamp` reprend le champ `submitted_at` (ou `created_at` à défaut).
  - `strategy_id` est résolu par rapprochement avec les identifiants connus des stratégies.
  - La clé `extra` conserve les champs bruts non affichés dans l'interface.

## Messages temps réel (WebSocket)

Le service de streaming transmet des événements au format JSON. Le client web supporte les
ressources suivantes :

### Mise à jour des stratégies

```jsonc
{
  "resource": "strategies",
  "items": [
    {
      "id": "92a939a2-57d5-4df3-a6c7-9d0b15efc2a4",
      "name": "Static",
      "status": "ERROR",
      "enabled": false,
      "last_error": "Order router indisponible"
    }
  ]
}
```

### Journaux d'exécution

Les événements de type `logs` (ou `executions`) peuvent contenir soit un champ `items` (tableau),
soit une entrée unique `entry` :

```jsonc
{
  "resource": "logs",
  "items": [
    {
      "timestamp": "2024-02-01T09:16:02.004Z",
      "message": "FILLED BTCUSDT (ordre order-success)",
      "status": "FILLED",
      "symbol": "BTCUSDT",
      "strategy_id": "92a939a2-57d5-4df3-a6c7-9d0b15efc2a4"
    }
  ]
}
```

Le client conserve au maximum 200 entrées et applique un filtrage par stratégie dans la console
interactive.

## Variables d'environnement

- `WEB_DASHBOARD_ORCHESTRATOR_BASE_URL` : URL de base de l'API orchestrateur (défaut
  `http://algo-engine:8000/`).
- `WEB_DASHBOARD_ORCHESTRATOR_TIMEOUT` : délai maximal (secondes) pour les appels HTTP.
- `WEB_DASHBOARD_MAX_LOG_ENTRIES` : nombre maximum d'entrées de log conservées côté client/serveur.

Ces paramètres garantissent la traçabilité des échanges entre le dashboard et l'orchestrateur.
