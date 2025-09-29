# Web Dashboard Service

Le service **web-dashboard** expose une interface FastAPI servant une page HTML
(Jinja2) permettant de visualiser l'activité des portefeuilles et la synthèse
de performance. Les sections ci-dessous récapitulent les jeux de données
alimentant la vue ainsi que les variables d'environnement utiles pour la
configuration.

## Sources de données

| Bloc du dashboard | Source | Détails |
| --- | --- | --- |
| Portefeuilles, transactions, alertes | `services/web-dashboard/app/data.py` | Données d'exemple construites côté service pour illustrer la présentation des portefeuilles et flux récents. |
| Métriques de performance | `reports-service` (`GET /reports/daily`) | Agrégation quotidienne retournant P\&L, drawdown et incidents. Le dashboard normalise les rendements à partir du champ d'exposition (`exposure`, `notional_exposure`, etc.) lorsqu'il est fourni afin de calculer un rendement composé et un ratio de Sharpe annualisé. |

Lorsque la réponse du reports-service ne contient pas d'exposition, le calcul du
Sharpe et du rendement cumulatif retombe sur les valeurs de P\&L brutes (sans
normalisation). Les cartes signalent également l'indisponibilité des métriques
lorsqu'un appel API échoue.

## Configuration

Le service s'appuie sur les variables suivantes :

- `WEB_DASHBOARD_STREAMING_BASE_URL`, `WEB_DASHBOARD_STREAMING_ROOM_ID`,
  `WEB_DASHBOARD_STREAMING_VIEWER_ID` : paramètres existants pour initialiser la
  section temps réel.
- `WEB_DASHBOARD_REPORTS_BASE_URL` : racine HTTP utilisée pour appeler
  `reports-service` (par défaut `http://reports:8000/`).
- `WEB_DASHBOARD_REPORTS_TIMEOUT` : délai (en secondes) appliqué aux requêtes
  HTTP vers le reports-service (par défaut `5.0`).

Le module `services/web-dashboard/app/data.py` encapsule ces appels via
`_fetch_performance_metrics()` et restitue un objet `PerformanceMetrics` injecté
dans le contexte Jinja. Toute adaptation (nouvelle source, transformation
supplémentaire) doit se faire dans ce module pour conserver une interface
centralisée.

## Tests

Aucun test spécifique n'est fourni pour le dashboard. L'ajout de tests FastAPI
ou de tests d'intégration ciblant l'appel au reports-service est recommandé si
le volume de logique métier augmente.
