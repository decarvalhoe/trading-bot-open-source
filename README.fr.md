[English](README.md) | [Français](README.fr.md)

# 🤖 Trading Bot Open Source

Un bot de trading automatisé et intelligent, conçu pour être **transparent**, **sécurisé** et **évolutif**. Ce projet open-source permet aux traders de tous niveaux d'automatiser leurs stratégies de trading avec une technologie moderne et fiable.

## 🎯 Qu'est-ce que ce projet ?

Ce trading bot est une plateforme complète qui permet de :

- **Automatiser vos stratégies de trading** sur différents marchés financiers
- **Gérer vos risques** avec des paramètres personnalisables
- **Suivre vos performances** en temps réel avec des tableaux de bord détaillés
- **Collaborer** avec une communauté de traders et développeurs

### Pourquoi choisir ce bot ?

- ✅ **100% Open Source** : Code transparent et auditable
- ✅ **Sécurité renforcée** : Authentification robuste et protection des données
- ✅ **Architecture moderne** : Microservices scalables et maintenables
- ✅ **Facilité d'utilisation** : Interface intuitive et documentation complète
- ✅ **Communauté active** : Support et contributions continues

## 🛠️ Architecture technique

Le projet utilise une **architecture microservices** moderne :

- **Services métier** : Chaque fonctionnalité est un service indépendant
- **Base de données** : PostgreSQL pour la persistance des données
- **Cache** : Redis pour les performances
- **API** : FastAPI pour des interfaces rapides et documentées
- **Conteneurisation** : Docker pour un déploiement simplifié

### Structure du projet

```
trading-bot-open-source/
├── services/           # Services métier (authentification, trading, etc.)
├── infra/             # Infrastructure (base de données, migrations)
├── libs/              # Bibliothèques partagées
├── scripts/           # Scripts d'automatisation
└── docs/              # Documentation
```

## 🧭 Panorama Fonctionnel

| Domaine | Périmètre | Statut | Prérequis d'Activation |
| --- | --- | --- | --- |
| Stratégies & recherche | Strategy Designer visuel, imports déclaratifs, assistant IA, API de backtest | Livré (designer & backtests), Bêta opt-in (assistant) | `make demo-up`, `pip install -r services/algo-engine/requirements.txt`, `AI_ASSISTANT_ENABLED=1`, `OPENAI_API_KEY` |
| Trading & exécution | Routeur d'ordres sandbox, script bootstrap, connecteurs marché (Binance, IBKR, DTC) | Livré (sandbox + Binance/IBKR), Expérimental (DTC) | `scripts/dev/bootstrap_demo.py`, identifiants exchanges selon besoin |
| Monitoring temps réel | Passerelle streaming, flux WebSocket InPlay, intégrations OBS/overlay | Livré (dashboard + alertes), Bêta (automatisation OBS) | Jetons de service (`reports`, `inplay`, `streaming`), secrets OAuth optionnels |
| Reporting & analytics | API rapports quotidiens, exports PDF, métriques de risque | Livré (rapports), Enrichissement en cours (dashboards risque) | Répertoire `data/generated-reports/` accessible ; stack Prometheus/Grafana |
| Notifications & alertes | Moteur d'alertes, service multi-canaux (Slack, email, Telegram, SMS) | Livré (cœur), Bêta (templates/throttling) | Variables d'environnement par canal, `NOTIFICATION_SERVICE_DRY_RUN` conseillé en staging |
| Marketplace & onboarding | API listings avec Stripe Connect, abonnements copy-trading, parcours d'onboarding | Bêta privée | Compte Stripe Connect, entitlements via billing service |

Retrouvez le détail des jalons dans [`docs/release-highlights/2025-12.md`](docs/release-highlights/2025-12.md).

## 🚀 Démarrage Rapide

### Installation de Base

```bash
# 1. Cloner le projet
git clone https://github.com/decarvalhoe/trading-bot-open-source.git
cd trading-bot-open-source

# 2. Installer les outils de développement
make setup

# 3. Démarrer l'environnement de développement
make dev-up

# 4. Vérifier que tout fonctionne (health auth-service)
curl http://localhost:8011/health

# 5. Arrêter l'environnement
make dev-down
```

### Stack de Démonstration

Pour explorer l'ensemble des services de monitoring et d'alertes, lancez la stack complète :

```bash
make demo-up
```

La commande construit les services FastAPI additionnels, applique les migrations Alembic et câble Redis/PostgreSQL avant d'exposer les ports suivants. Activez l'assistant IA stratégies en option et les connecteurs avec :

```bash
pip install -r services/algo-engine/requirements.txt
export AI_ASSISTANT_ENABLED=1
export OPENAI_API_KEY="sk-votre-cle"
```

**Services Disponibles :**
- `8013` — `order-router` (plans d'exécution et courtiers simulés)
- `8014` — `algo-engine` (catalogue de stratégies, backtesting, assistant IA optionnel sur `/strategies/generate`)
- `8015` — `market_data` (cotations spot, carnets d'ordres et webhooks TradingView)
- `8016` — `reports` (rapports de risque et génération PDF)
- `8017` — `alert_engine` (évaluation de règles avec ingestion streaming)
- `8018` — `notification-service` (historique de livraison d'alertes)
- `8019` — `streaming` (ingestion de salle + diffusion WebSocket)
- `8020` — `streaming_gateway` (flux OAuth overlay et pont TradingView)
- `8021` — `inplay` (mises à jour WebSocket de watchlist)
- `8022` — `web-dashboard` (tableau de bord HTML soutenu par les APIs reports + alertes)

Les artefacts générés sont stockés dans `data/generated-reports/` (exports PDF) et `data/alert-events/` (base de données SQLite partagée pour l'historique des alertes). Les jetons de service par défaut (`reports-token`, `inplay-token`, `demo-alerts-token`) et les secrets d'API externes peuvent être surchargés via les variables d'environnement avant de lancer la stack.

Arrêtez tous les conteneurs avec :

```bash
make demo-down
```

### Lancer le Flux de Bout en Bout

Une fois la stack en cours d'exécution, vous pouvez exercer le parcours complet inscription → trading avec le script d'aide :

```bash
scripts/dev/bootstrap_demo.py BTCUSDT 0.25 --order-type market
```

La commande provisionne un compte de démonstration, assigne les entitlements, configure une stratégie, route un ordre, génère un rapport PDF, enregistre une alerte et publie un événement streaming. Le JSON émis résume tous les identifiants créés (utilisateur, stratégie, ordre, alerte, emplacement du rapport) ainsi que les jetons JWT associés au profil de démonstration.

`scripts/dev/run_mvp_flow.py` enveloppe maintenant simplement cette commande pour la compatibilité ascendante.

### Migrations de Base de Données

Utilisez les assistants Makefile pour gérer les migrations Alembic localement (les commandes utilisent par défaut `postgresql+psycopg2://trading:trading@localhost:5432/trading`, surchargez avec `ALEMBIC_DATABASE_URL=<votre-url>` si nécessaire) :

```bash
# Générer une nouvelle révision
make migrate-generate message="add user preferences"

# Générer une révision trading directement avec Alembic (génère automatiquement les modèles orders/executions)
ALEMBIC_DATABASE_URL=postgresql+psycopg2://trading:trading@localhost:5432/trading \
  alembic -c infra/migrations/alembic.ini revision --autogenerate -m "add trading orders and executions tables"

# Appliquer les migrations (par défaut vers head)
make migrate-up

# Revenir à la révision précédente (surchargez DOWN_REVISION pour cibler une autre)
make migrate-down
```

Les services Docker appliquent maintenant automatiquement les migrations au démarrage via [`scripts/run_migrations.sh`](scripts/run_migrations.sh), garantissant que le schéma de base de données est à jour avant chaque démarrage d'application.

## 📈 État d'Avancement du Projet

### Phase 1 : Fondations (✅ Terminée)
**Objectif** : Mettre en place l'infrastructure technique de base

- ✅ **Configuration du projet** : Repository, outils de développement, CI/CD
- ✅ **Service de configuration** : Gestion centralisée des paramètres

*Résultat* : L'infrastructure technique est opérationnelle et prête pour le développement.

### Phase 2 : Authentification et Utilisateurs (✅ Terminée)
**Objectif** : Permettre aux utilisateurs de créer des comptes et se connecter de manière sécurisée

- ✅ **Système d'authentification** : Inscription, connexion, sécurité JWT, MFA TOTP
- ✅ **Gestion des profils** : Création et modification des profils avec masquage selon les entitlements
- ✅ **Documentation parcours complet** : Consolidation de l'OpenAPI et du guide UX pour l'onboarding

*Résultat* : Les utilisateurs peuvent créer un compte sécurisé, activer leur profil et préparer l'enrôlement MFA.

### Phase 3 : Stratégies de Trading (✅ Terminée)
**Objectif** : Permettre la création et l'exécution de stratégies de trading

- ✅ **Moteur de stratégies** : Catalogue persistant, import déclaratif et API de backtesting
- ✅ **Strategy Designer visuel** : Interface drag-and-drop pour la création de stratégies
- ✅ **Assistant IA stratégies** : Génération de stratégies via OpenAI à partir de langage naturel
- ✅ **Connecteurs de marché** : Adaptateurs sandbox Binance/IBKR avec limites partagées
- ✅ **Gestion des ordres** : Persistance et implémentation de l'historique d'exécutions

### Phase 4 : Monitoring et Analytics (✅ Terminée)
**Objectif** : Fournir des outils d'analyse et de suivi des performances

- ✅ **Service de rapports** : Calculs de métriques de performance, API et tests unitaires
- ✅ **Service de notifications** : Dispatcher multi-canaux avec support Slack, email, Telegram, SMS
- ✅ **Dashboard web** : Composants React, intégration streaming et affichage des métriques
- ✅ **Infrastructure d'observabilité** : Configuration Prometheus/Grafana et dashboard FastAPI

### Phase 5 : Marketplace et Communauté (🔄 Bêta)
**Objectif** : Créer un écosystème communautaire pour le partage de stratégies

- 🔄 **Marketplace de stratégies** : API de listings avec intégration Stripe Connect
- 🔄 **Copy Trading** : Suivi de stratégies par abonnement
- 🔄 **Fonctionnalités communautaires** : Évaluations de stratégies, avis et fonctionnalités sociales

## 📊 Métriques du Projet (Décembre 2025)

- **Lignes de code** : 25 000+ (Python, JavaScript, TypeScript)
- **Nombre de services** : 22 microservices
- **Nombre de commits** : 200+
- **Nombre de tests** : 150+ fichiers de test
- **Contributeurs** : 3+ développeurs actifs

## 📊 Revue 2025 et Prochaines Étapes

Une revue technique complète du repository a été menée en novembre 2025. Le projet a considérablement évolué avec l'ajout d'outils de création visuelle de stratégies, d'assistance IA et de capacités de monitoring complètes.

- **Réalisations clés** : Strategy Designer visuel, génération de stratégies par IA, dashboard complet, notifications multi-canaux
- **Focus actuel** : Lancement bêta marketplace, analytics avancés, fonctionnalités communautaires
- **Prochaines priorités** : Application mobile, gestion de risque avancée, fonctionnalités institutionnelles

Retrouvez le rapport détaillé, la feuille de route et le backlog dans :

- [`docs/reports/2025-11-code-review.md`](docs/reports/2025-11-code-review.md)
- [`docs/project-evaluation.md`](docs/project-evaluation.md)
- [`docs/tasks/2025-q4-backlog.md`](docs/tasks/2025-q4-backlog.md)
- [`docs/release-highlights/2025-12.md`](docs/release-highlights/2025-12.md)

## 🗺️ Feuille de Route et Prochaines Étapes

### Priorités à Court Terme (0-3 mois)

1. **Lancement Marketplace**
   - Finaliser l'intégration Stripe Connect
   - Lancer la marketplace bêta avec des créateurs de stratégies sélectionnés
   - Implémenter les abonnements copy trading

2. **Analytics Avancés**
   - Métriques de risque et analytics de portefeuille améliorés
   - Analyse d'attribution de performance
   - Fonctionnalités de backtesting avancées

3. **Expérience Mobile**
   - Améliorations du design web responsive
   - Fonctionnalités Progressive Web App (PWA)
   - Interface de trading optimisée mobile

### Objectifs à Moyen Terme (3-6 mois)

1. **Fonctionnalités Institutionnelles**
   - Comptes multi-utilisateurs et permissions
   - Conformité et reporting avancés
   - Gestion de risque de niveau institutionnel

2. **Fonctionnalités IA Avancées**
   - Recommandations d'optimisation de stratégies
   - Détection de régimes de marché
   - Ajustement automatique du risque

3. **Expansion de l'Écosystème**
   - Intégrations d'exchanges supplémentaires
   - Système de plugins tiers
   - Marketplace API pour développeurs

## 🤝 Comment Contribuer ?

Nous accueillons toutes les contributions ! Que vous soyez :

- **Trader expérimenté** : Partagez vos stratégies et votre expertise
- **Développeur** : Améliorez le code et ajoutez de nouvelles fonctionnalités
- **Testeur** : Aidez-nous à identifier et corriger les bugs
- **Designer** : Améliorez l'expérience utilisateur

### Étapes pour Contribuer

1. **Consultez** les [issues ouvertes](https://github.com/decarvalhoe/trading-bot-open-source/issues)
2. **Lisez** le guide de contribution dans `CONTRIBUTING.md`
3. **Créez** une branche pour votre contribution
4. **Soumettez** une pull request avec vos améliorations

## 📞 Support et Communauté

- **Issues GitHub** : Pour signaler des bugs ou proposer des fonctionnalités
- **Discussions** : Pour échanger avec la communauté
- **Documentation** : Guide complet dans le dossier `docs/`

## 📄 Licence

Ce projet est sous licence MIT - voir le fichier `LICENSE` pour plus de détails.

---

> **Développé avec ❤️ par decarvalhoe et la communauté open-source**  
> Dernière mise à jour : Décembre 2025
