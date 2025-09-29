# Contrat d'acheminement d'ordre sandbox

Ce document décrit le contrat REST utilisé entre un algorithme et le service
`order-router` afin de déposer un ordre standardisé dans l'environnement
sandbox. Les structures `ExecutionIntent` (requête) et `ExecutionReport`
(réponse) sont définies dans `schemas/order_router.py` et servent également de
schémas FastAPI.

## Transport et chemin

- **Méthode** : `POST`
- **Chemin** : `/orders`
- **Code succès** : `201 Created`
- **Codes d'erreur** :
  - `400 Bad Request` : validation de schéma ou rejet du moteur de risque.
  - `403 Forbidden` : limites journalières dépassées ou privilèges manquants.
  - `404 Not Found` : broker ou paire non supportés.
  - `500 Internal Server Error` : échec de persistance de l'ordre.

## Spécification OpenAPI

```yaml
post:
  summary: Route un ordre sandbox et renvoie un rapport d'exécution.
  operationId: routeSandboxOrder
  requestBody:
    required: true
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ExecutionIntent'
  responses:
    '201':
      description: Rapport d'exécution initial.
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ExecutionReport'
    '400':
      description: Requête invalide ou verrouillage risque.
    '403':
      description: Limite quotidienne dépassée ou capability manquante.
    '404':
      description: Broker ou paire inconnus.
    '500':
      description: Persistance de l'ordre impossible.
```

## `ExecutionIntent`

Payload enrichi combinant l'ordre standardisé et un contexte risque facultatif.

| Champ | Type | Obligatoire | Description |
| --- | --- | --- | --- |
| `broker` | `string` | oui | Identifiant du broker sandbox ciblé. |
| `venue` | `string` | oui | Venue d'exécution (`ExecutionVenue`). |
| `symbol` | `string` | oui | Symbole négocié (ex : `BTCUSDT`). |
| `side` | `string` | oui | Sens de l'ordre (`buy`/`sell`). |
| `quantity` | `number` | oui | Quantité positive à router. |
| `order_type` | `string` | oui | `market` ou `limit`. |
| `price` | `number` | non | Prix limite (> 0) requis pour un ordre `limit`. |
| `time_in_force` | `string` | non | Par défaut `GTC`. |
| `client_order_id` | `string` | non | Identifiant externe (36 caractères max). |
| `tags` | `array[string]` | non | Labels libres propagés au rapport. |
| `account_id` | `string` | non | Référence compte utilisée pour les règles de risque. |
| `risk` | `object` | non | Voir `RiskOverrides`. |

### `RiskOverrides`

| Champ | Type | Obligatoire | Description |
| --- | --- | --- | --- |
| `account_id` | `string` | non | Compte cible (défaut : `default`). |
| `realized_pnl` | `number` | non | PnL réalisé utilisé par le moteur de risque. |
| `unrealized_pnl` | `number` | non | PnL latent transmis au moteur. |
| `stop_loss` | `number` | non | Seuil de stop-loss (> 0) à appliquer. |

### Exemple de requête

```json
{
  "broker": "binance",
  "venue": "binance.spot",
  "symbol": "BTCUSDT",
  "side": "buy",
  "quantity": 0.5,
  "order_type": "limit",
  "price": 29500,
  "time_in_force": "GTC",
  "tags": ["mvp", "sandbox"],
  "client_order_id": "algo-1234",
  "account_id": "demo-account",
  "risk": {
    "account_id": "demo-account",
    "realized_pnl": -1250.5,
    "unrealized_pnl": 320.0,
    "stop_loss": 45000
  }
}
```

## `ExecutionReport`

Accusé d'exécution renvoyé immédiatement après la soumission ; il reprend les
champs standards partagés avec `schemas/market.py`.

| Champ | Type | Description |
| --- | --- | --- |
| `order_id` | `string` | Identifiant de l'ordre côté broker sandbox. |
| `status` | `string` | État initial (`accepted`, `filled`, `partially_filled`, etc.). |
| `broker` | `string` | Broker ayant reçu l'ordre. |
| `venue` | `string` | Venue d'exécution. |
| `symbol` | `string` | Symbole négocié. |
| `side` | `string` | Sens de l'ordre. |
| `quantity` | `number` | Quantité originale. |
| `filled_quantity` | `number` | Quantité exécutée à ce stade. |
| `avg_price` | `number` | Prix moyen pondéré si disponible. |
| `submitted_at` | `string(date-time)` | Horodatage ISO 8601 de soumission. |
| `fills` | `array` | Liste des exécutions (`quantity`, `price`, `timestamp`). |
| `tags` | `array[string]` | Tags propagés depuis l'intent. |

### Exemple de réponse (`201 Created`)

```json
{
  "order_id": "BN-1",
  "status": "filled",
  "broker": "binance",
  "venue": "binance.spot",
  "symbol": "BTCUSDT",
  "side": "buy",
  "quantity": 0.5,
  "filled_quantity": 0.5,
  "avg_price": 29500.0,
  "submitted_at": "2023-11-15T10:32:41Z",
  "fills": [
    {
      "quantity": 0.5,
      "price": 29500.0,
      "timestamp": "2023-11-15T10:32:41Z"
    }
  ],
  "tags": ["mvp", "sandbox"]
}
```

Ces spécifications garantissent que l'orchestrateur MVP et les clients
externes consomment le même contrat pour initier et suivre l'exécution d'ordres
via le routeur sandbox.
