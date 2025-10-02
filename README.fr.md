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

## 🧭 Panorama fonctionnel

| Domaine | Périmètre | Statut | Prérequis d'activation |
| --- | --- | --- | --- |
| Stratégies & recherche | Strategy Designer visuel, imports déclaratifs, assistant IA, API de backtest | Livré (designer & backtests), Bêta opt-in (assistant) | `make demo-up`, `pip install -r services/algo-engine/requirements.txt`, `AI_ASSISTANT_ENABLED=1`, `OPENAI_API_KEY` |
| Trading & exécution | Routeur d'ordres sandbox, script bootstrap, connecteurs marché (Binance, IBKR, DTC) | Livré (sandbox + Binance/IBKR), Expérimental (DTC) | `scripts/dev/bootstrap_demo.py`, identifiants exchanges selon besoin |
| Monitoring temps réel | Passerelle streaming, flux WebSocket InPlay, intégrations OBS/overlay | Livré (dashboard + alertes), Bêta (automatisation OBS) | Jetons de service (`reports`, `inplay`, `streaming`), secrets OAuth optionnels |
| Reporting & analytics | API rapports quotidiens, exports PDF, métriques de risque | Livré (rapports), Enrichissement en cours (dashboards risque) | Répertoire `data/generated-reports/` accessible ; stack Prometheus/Grafana |
| Notifications & alertes | Moteur d'alertes, service multi-canaux (Slack, email, Telegram, SMS) | Livré (cœur), Bêta (templates/throttling) | Variables d'environnement par canal, `NOTIFICATION_SERVICE_DRY_RUN` conseillé en staging |
| Marketplace & onboarding | API listings avec Stripe Connect, abonnements copy-trading, parcours d'onboarding | Bêta privée | Compte Stripe Connect, entitlements via billing service |

Retrouvez le détail des jalons dans [`docs/release-highlights/2025-12.md`](docs/release-highlights/2025-12.md).

## 🚀 État d'avancement du projet

### Phase 1 : Fondations (✅ Terminée)
**Objectif** : Mettre en place l'infrastructure technique de base

- ✅ **Configuration du projet** : Repository, outils de développement, CI/CD

- **Points forts** : base d'authentification avancée (MFA TOTP, rôles), stack d'observabilité (logs + Prometheus/Grafana), Makefile facilitant l'onboarding, documentation structurée.
- **Points d'attention** : services de trading encore en mémoire, couverture de tests multi-services limitée, procédures opérationnelles de gestion des secrets à formaliser.
- **Priorités recommandées (0-3 mois)** : consolider la doc E2E auth/user, persister les artefacts trading, étendre les tests (unitaires + contractuels), publier les playbooks secrets et observabilité.

Retrouvez le rapport détaillé, la feuille de route et le backlog dans :

- [`docs/reports/2025-11-code-review.md`](docs/reports/2025-11-code-review.md)
- [`docs/project-evaluation.md`](docs/project-evaluation.md)
- [`docs/tasks/2025-q4-backlog.md`](docs/tasks/2025-q4-backlog.md)

## 🛠️ Pour les développeurs

### Démarrage rapide

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

### Stack de démonstration

Pour observer l'ensemble monitoring + alertes, lancez la stack complète :

```bash
make demo-up
```

La commande construit les services FastAPI additionnels, applique les migrations et
câble Redis/PostgreSQL. Activez l'assistant IA en option via :

```bash
pip install -r services/algo-engine/requirements.txt
export AI_ASSISTANT_ENABLED=1
export OPENAI_API_KEY="sk-votre-cle"
```

Les artefacts générés sont déposés dans `data/generated-reports/` (PDF) et
`data/alert-events/` (historique d'alertes SQLite).

#### Lancer le parcours de démonstration complet

```bash
scripts/dev/bootstrap_demo.py BTCUSDT 0.25 --order-type market
```

La commande crée un compte de démonstration, assigne les entitlements nécessaires,
active le profil, configure une stratégie, route un ordre, génère un rapport PDF,
enregistre une alerte et publie un événement streaming. Le JSON retourné résume les
identifiants utiles (utilisateur, stratégie, ordre, alerte, chemin du rapport) ainsi
que les tokens JWT associés. Rejouez le flux depuis le notebook
[`docs/tutorials/backtest-sandbox.ipynb`](docs/tutorials/backtest-sandbox.ipynb).
Le script historique `scripts/dev/run_mvp_flow.py` redirige désormais vers cette
implémentation.

### Architecture technique

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

## 🤝 Comment contribuer ?

Nous accueillons toutes les contributions ! Que vous soyez :

- **Trader expérimenté** : Partagez vos stratégies et votre expertise
- **Développeur** : Améliorez le code et ajoutez de nouvelles fonctionnalités
- **Testeur** : Aidez-nous à identifier et corriger les bugs
- **Designer** : Améliorez l'expérience utilisateur

### Étapes pour contribuer

1. **Consultez** les [issues ouvertes](https://github.com/decarvalhoe/trading-bot-open-source/issues)
2. **Lisez** le guide de contribution dans `CONTRIBUTING.md`
3. **Créez** une branche pour votre contribution
4. **Soumettez** une pull request avec vos améliorations

## 🌟 Points marquants & tutoriels

- Consultez la synthèse des fonctionnalités et propriétaires dans [docs/release-highlights/2025-12.md](docs/release-highlights/2025-12.md).
- Les notebooks et vidéos à jour sont listés dans [docs/tutorials/README.md](docs/tutorials/README.md) pour accompagner l'onboarding.
- Les validations des responsables de service et la communication interne sont tracées dans [docs/governance/release-approvals/2025-12.md](docs/governance/release-approvals/2025-12.md) et [docs/communications/2025-12-release-update.md](docs/communications/2025-12-release-update.md).

## 📞 Support et communauté

- **Issues GitHub** : Pour signaler des bugs ou proposer des fonctionnalités
- **Discussions** : Pour échanger avec la communauté
- **Documentation** : Guide complet dans le dossier `docs/`

## 📄 Licence

Ce projet est sous licence MIT - voir le fichier `LICENSE` pour plus de détails.

---

> **Développé avec ❤️ par decarvalhoe et la communauté open-source**
> Dernière mise à jour : Novembre 2025
- ✅ **Environnement de développement** : Docker, base de données, services
- ✅ **Service de configuration** : Gestion centralisée des paramètres

*Résultat* : L'infrastructure technique est opérationnelle et prête pour le développement.

### Phase 2 : Authentification et Utilisateurs (✅ Terminée)
**Objectif** : Permettre aux utilisateurs de créer des comptes et se connecter de manière sécurisée

- ✅ **Système d'authentification** : Inscription, connexion, sécurité JWT, MFA TOTP
- ✅ **Gestion des profils** : Création et modification des profils avec masquage selon les entitlements
- ✅ **Documentation parcours complet** : Consolidation de l'OpenAPI et du guide UX pour l'onboarding

*Résultat* : Les utilisateurs peuvent créer un compte sécurisé, activer leur profil et préparer l'enrôlement MFA.

### Phase 3 : Stratégies de Trading (🔄 En cours - 80%)
**Objectif** : Permettre la création et l'exécution de stratégies de trading

- ✅ **Moteur de stratégies** : Catalogue en mémoire, import déclaratif et API de backtesting
- ✅ **Strategy Designer visuel (bêta)** : Canvas web exportant YAML/Python compatibles avec l'algo-engine
- 🟡 **Assistant IA (bêta opt-in)** : Endpoint `/strategies/generate` activé avec LangChain/OpenAI et variables d'environnement
- ✅ **Connecteurs de marché** : Adaptateurs sandbox Binance/IBKR avec limites partagées ; stub Sierra Chart DTC en expérimentation
- 🔄 **Gestion des ordres** : Persistance et historique d'exécutions en cours d'implémentation

### Phase 4 : Monitoring et Analytics (🔄 En cours - 53%)
**Objectif** : Fournir des outils d'analyse et de suivi des performances

- ✅ **Dashboards temps réel** : Passerelle streaming + flux InPlay alimentent setups live, portefeuilles et alertes
- ✅ **Service de rapports** (65%) : Calculs de métriques, exports PDF et API consommée par le dashboard
- 🟡 **Service de notifications** (45%) : Diffusion multi-canale (Slack/email/Telegram/SMS) avec mode dry-run
- 🟡 **Infrastructure d'observabilité** (70%) : Dashboards Prometheus/Grafana disponibles ; automatisation OBS ciblée T1 2026

*Prochaines étapes* : Durcir le throttling des notifications, enrichir les dashboards Grafana et documenter les bonnes pratiques OBS.

## 📊 Métriques du projet (Septembre 2025)

- **Lignes de code** : 17 676 (Python uniquement)
- **Nombre de services** : 20 microservices
- **Nombre de commits** : 129
- **Nombre de tests** : 26 fichiers de test unitaire
- **Contributeurs** : 2 développeurs actifs

## 🗺️ Feuille de route et prochaines étapes

### Priorités à court terme (0-1 mois)

1. **Finaliser la Phase 4 : Monitoring et Analytics**
   - Compléter le service de notifications avec tests unitaires
   - Enrichir le dashboard web avec plus de visualisations
   - Configurer les alertes dans Prometheus/Grafana
   - Intégrer tous les services de la Phase 4 dans docker-compose.yml

2. **Améliorer la documentation**
   - Consolider la documentation OpenAPI pour tous les services
   - Créer des guides utilisateur pour les fonctionnalités de monitoring
   - Documenter les procédures opérationnelles pour la gestion des alertes

### Objectifs à moyen terme (1-3 mois)

1. **Optimisation des performances**
   - Améliorer les performances du moteur de stratégies
   - Optimiser les requêtes de base de données
   - Mettre en place un système de cache distribué

2. **Extension des connecteurs de marché**
   - Ajouter de nouveaux connecteurs pour d'autres exchanges
   - Implémenter des adaptateurs pour les marchés traditionnels
   - Améliorer la gestion des limites de rate

3. **Enrichissement des stratégies**
   - Développer une bibliothèque de stratégies prêtes à l'emploi
   - Créer un éditeur visuel de stratégies
   - Implémenter des outils avancés de backtesting

## 🛠️ Pour les développeurs
