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

Deux familles de tests couvrent le service :

- Tests d'API FastAPI (`pytest services/web-dashboard/tests/test_portfolio_history.py`).
- Scénarios de bout en bout Playwright pilotant le navigateur pour vérifier
  l'affichage des métriques, les mises à jour temps réel simulées et quelques
  contrôles d'accessibilité (`make web-dashboard-e2e`).

Avant la première exécution des scénarios Playwright, installez les dépendances
Python (`pip install -r services/web-dashboard/requirements-dev.txt`) puis les
binaires navigateur (`python -m playwright install chromium`). Une fois ces
pré-requis en place, la commande `make web-dashboard-e2e` démarre le serveur
FastAPI en tâche de fond et exécute les tests.
