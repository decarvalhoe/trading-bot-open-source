# Observabilité des microservices

Cette section décrit la configuration commune ajoutée à l'ensemble des services FastAPI :

- une journalisation JSON corrélée sur stdout ;
- un endpoint `/metrics` compatible Prometheus ;
- le stack de supervision Prometheus + Grafana fourni via `docker-compose`.

## Journalisation JSON corrélée

Chaque service configure désormais automatiquement la journalisation structurée à l'import du module FastAPI. Les logs sont émis au format JSON sur `stdout` et incluent systématiquement les champs suivants :

| Champ | Description |
| --- | --- |
| `timestamp` | Horodatage ISO 8601 (UTC, précision milliseconde). |
| `level` | Niveau de log (`INFO`, `ERROR`, etc.). |
| `logger` | Nom du logger Python émetteur. |
| `service` | Identifiant du service (ex. `auth-service`). |
| `message` | Contenu textuel du log. |
| `correlation_id` | Identifiant de corrélation propagé via l'en-tête `X-Correlation-ID` (généré si absent). |
| `request_id` | Identifiant unique généré pour chaque requête HTTP. |

Les erreurs incluent également un champ `exception` avec la trace formatée. Toute donnée supplémentaire transmise via `logging.Logger.extra` est sérialisée (conversion en `str` en dernier recours).

### Propagation

Le middleware `RequestContextMiddleware` recherche les en-têtes `X-Correlation-ID` ou `X-Request-ID`. À défaut, un UUID est créé et ajouté à la réponse. Les identifiants restent disponibles dans le code applicatif via `libs.observability.logging.get_correlation_id()` et `get_request_id()`.

## Endpoint `/metrics`

Tous les services ajoutent automatiquement le middleware Prometheus qui instrumente :

- `http_requests_total{service,method,path,status}` : compteur par statut HTTP ;
- `http_request_latency_seconds{service,method,path}` : histogramme de latence avec buckets prédéfinis.

L'endpoint `/metrics` est exclu de la documentation OpenAPI mais renvoie les métriques au format exposition Prometheus.

## Prometheus & Grafana

Le fichier `docker-compose.yml` expose deux nouveaux services :

- `prometheus` (port `9090`) chargé avec `infra/prometheus/prometheus.yml` et les règles d'alerte `infra/prometheus/alert_rules.yml` ;
- `grafana` (port `3000`) pré-provisionné avec une source de données Prometheus et le tableau de bord `docs/observability/dashboards/fastapi-overview.json`.

### Démarrage rapide

```bash
docker-compose up prometheus grafana
```

Accédez à Grafana via http://localhost:3000 (login/par défaut `admin`/`admin`). Le tableau de bord **FastAPI - Vue d'ensemble** affiche le débit, la latence P95 et le taux d'erreurs 5xx filtrables par service.

## Alerting

Les règles Prometheus fournies déclenchent :

- **FastAPIHighLatency** : latence moyenne > 500 ms sur 5 minutes (`severity: warning`).
- **FastAPIHighErrorRate** : taux de 5xx > 5 % sur 10 minutes (`severity: critical`).

La procédure d'escalade associée est détaillée dans `docs/operations/alerting.md`.
