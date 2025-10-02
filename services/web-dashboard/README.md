# Web Dashboard Service

Le service **web-dashboard** expose une interface FastAPI servant une page HTML
(Jinja2) permettant de visualiser l'activité des portefeuilles et la synthèse
de performance. Les sections ci-dessous récapitulent les jeux de données
alimentant la vue ainsi que les variables d'environnement utiles pour la
configuration.

## Pages disponibles

- `/dashboard` : vue historique et temps réel existante.
- `/strategies` : éditeur visuel React permettant de composer des stratégies et de
  les sauvegarder via l'endpoint `/strategies/save` (voir ci-dessous).
- `/account` : page statique dédiée à la gestion utilisateur (connexion) et à la
  configuration des clés API exchanges.

Le composant principal du designer est `StrategyDesigner` situé dans
`services/web-dashboard/src/strategies/designer/`. L'éditeur expose une palette
de blocs (conditions, indicateurs, opérateurs logiques, actions, temporisations)
et sérialise automatiquement l'arbre construit vers YAML ou Python afin de
rester compatible avec l'API `/strategies/import` de l'algo-engine.

## Sources de données

| Bloc du dashboard | Source | Détails |
| --- | --- | --- |
| Portefeuilles, transactions | `order-router` (`GET /orders/log`) via `services/web-dashboard/app/order_router_client.py` | L'historique d'ordres est agrégé pour reconstituer les positions et transactions par portefeuille. En cas d'échec réseau, le service retombe sur un instantané statique et expose cette information via le champ `data_sources`. |
| Alertes | `alert-engine` (`GET /alerts`) | Les alertes actives sont récupérées côté moteur et mises en cache en mémoire avec une liste de secours si l'appel échoue. |
| Métriques de performance | `reports-service` (`GET /reports/daily`) | Agrégation quotidienne retournant P\&L, drawdown et incidents. Le dashboard normalise les rendements à partir du champ d'exposition (`exposure`, `notional_exposure`, etc.) lorsqu'il est fourni afin de calculer un rendement composé et un ratio de Sharpe annualisé. |
| Setups InPlay | `services/inplay` (`GET /inplay/watchlists/{id}` + WebSocket `/inplay/ws`) | Les setups incluent un champ `session` (`london`, `new_york`, `asia`). Le dashboard expose un sélecteur pour filtrer l'affichage par session et peut recharger un instantané via `?session=`. |

Lorsque la réponse du reports-service ne contient pas d'exposition, le calcul du
Sharpe et du rendement cumulatif retombe sur les valeurs de P\&L brutes (sans
normalisation). Les cartes signalent également l'indisponibilité des métriques
lorsqu'un appel API échoue. Les sections « Portefeuilles » et « Transactions »
reposent désormais sur le routeur d'ordres ; si l'appel `/orders/log` échoue,
le contexte injecte `data_sources["portfolios"] = data_sources["transactions"] = "fallback"`
et l'interface affiche un message « mode dégradé ».

## Configuration

Le service s'appuie sur les variables suivantes :

- `WEB_DASHBOARD_STREAMING_BASE_URL`, `WEB_DASHBOARD_STREAMING_ROOM_ID`,
  `WEB_DASHBOARD_STREAMING_VIEWER_ID` : paramètres existants pour initialiser la
  section temps réel.
- `WEB_DASHBOARD_REPORTS_BASE_URL` : racine HTTP utilisée pour appeler
  `reports-service` (par défaut `http://reports:8000/`).
- `WEB_DASHBOARD_REPORTS_TIMEOUT` : délai (en secondes) appliqué aux requêtes
  HTTP vers le reports-service (par défaut `5.0`).
- `WEB_DASHBOARD_ORDER_ROUTER_BASE_URL` : racine HTTP utilisée pour joindre
  `order-router` (par défaut `http://order-router:8000/`).
- `WEB_DASHBOARD_ORDER_ROUTER_TIMEOUT` : délai appliqué aux requêtes vers
  `order-router` (par défaut `5.0`).
- `WEB_DASHBOARD_ORDER_LOG_LIMIT` : nombre maximal d'ordres récupérés pour
  reconstruire les portefeuilles (par défaut `200`).
- `WEB_DASHBOARD_MAX_TRANSACTIONS` : nombre d'exécutions affichées dans la
  section « Transactions récentes » (par défaut `25`).
- `WEB_DASHBOARD_ALGO_ENGINE_URL` : URL de base utilisée pour relayer les
  stratégies vers l'algo-engine (par défaut `http://algo-engine:8000/`).
- `WEB_DASHBOARD_ALGO_ENGINE_TIMEOUT` : délai appliqué aux requêtes de
  sauvegarde des stratégies (par défaut `5.0`).

Le module `services/web-dashboard/app/data.py` encapsule ces appels via
`_fetch_performance_metrics()` et restitue un objet `PerformanceMetrics` injecté
dans le contexte Jinja. Toute adaptation (nouvelle source, transformation
supplémentaire) doit se faire dans ce module pour conserver une interface
centralisée.

### Étendre le Strategy Designer

Les composants du designer sont regroupés dans `src/strategies/designer/`. Chaque
bloc est décrit dans `designerConstants.js` (catégorie, description, configuration
par défaut). Pour ajouter un nouveau type de bloc :

1. Déclarer sa définition dans `designerConstants.js` (type, label, catégorie,
   types enfants acceptés).
2. Étendre `StrategyBlock.jsx` afin de rendre les champs de configuration
   nécessaires.
3. Adapter `serializer.js` pour inclure le nouveau bloc dans la structure YAML /
   Python exportée.

Des tests unitaires (`services/web-dashboard/test/strategy-designer.test.jsx`)
utilisent React Testing Library pour couvrir la composition de blocs et leur
imbriquement. Le scénario Playwright `services/web-dashboard/tests/e2e/test_strategies_designer.py`
valide la création d'une stratégie complète et la propagation de la requête vers
le backend FastAPI.

### Filtrage des sessions InPlay

La section « Setups en temps réel » propose un sélecteur de session (`Toutes les sessions`, `Londres`, `New York`, `Asie`). Le filtrage est appliqué côté navigateur et déclenche, si besoin, une requête `GET /inplay/watchlists/{id}?session=...` pour synchroniser l'instantané InPlay. Sans sélection particulière, toutes les sessions restent visibles et les mises à jour temps réel continuent d'être diffusées via le WebSocket.

## Tests

Deux familles de tests couvrent le service :

- Tests d'API FastAPI (`pytest services/web-dashboard/tests/test_portfolio_history.py`).
- Scénarios de bout en bout Playwright pilotant le navigateur pour vérifier
  l'affichage des métriques, les mises à jour temps réel simulées, la page
  « Stratégies » et quelques contrôles d'accessibilité (`make web-dashboard-e2e`).

Avant la première exécution des scénarios Playwright, installez les dépendances
Python (`pip install -r services/web-dashboard/requirements-dev.txt`) puis les
binaires navigateur (`python -m playwright install chromium`). Une fois ces
pré-requis en place, la commande `make web-dashboard-e2e` démarre le serveur
FastAPI en tâche de fond et exécute les tests.
