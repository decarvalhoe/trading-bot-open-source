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

## 🚀 État d'avancement du projet

### Phase 1 : Fondations (✅ Terminée)
**Objectif** : Mettre en place l'infrastructure technique de base

- ✅ **Configuration du projet** : Repository, outils de développement, CI/CD
- ✅ **Environnement de développement** : Docker, base de données, services
- ✅ **Service de configuration** : Gestion centralisée des paramètres

*Résultat* : L'infrastructure technique est opérationnelle et prête pour le développement.

### Phase 2 : Authentification et Utilisateurs (✅ Cœur fonctionnel prêt)
**Objectif** : Permettre aux utilisateurs de créer des comptes et se connecter de manière sécurisée

- ✅ **Système d'authentification** : Inscription, connexion, sécurité JWT, MFA TOTP
- ✅ **Gestion des profils** : Création et modification des profils avec masquage selon les entitlements
- 🔄 **Documentation parcours complet** : Consolider l'OpenAPI et un guide UX pour l'onboarding

*Résultat* : Les utilisateurs peuvent créer un compte sécurisé, activer leur profil et préparer l'enrôlement MFA.

### Phase 3 : Stratégies de Trading (🔄 En cours)
**Objectif** : Permettre la création et l'exécution de stratégies de trading

- 🔄 **Moteur de stratégies** : Catalogue en mémoire, import déclaratif et API de backtesting
- 🔄 **Connecteurs de marché** : Adaptateurs sandbox Binance/IBKR avec limites partagées
- 📋 **Gestion des ordres** : Persistance et historique d'exécutions à implémenter

### Phase 4 : Monitoring et Analytics (📋 Planifiée)
**Objectif** : Fournir des outils d'analyse et de suivi des performances

- 📋 **Tableaux de bord** : Visualisation des performances en temps réel
- 📋 **Alertes et notifications** : Système d'alertes personnalisables
- 📋 **Rapports détaillés** : Analyses approfondies des résultats

## 📊 Évaluation 2025 & actions futures

Une revue technique complète du dépôt a été réalisée en novembre 2025. Elle confirme la solidité de l'architecture actuelle (microservices FastAPI, middleware d'entitlements partagé) et identifie les chantiers prioritaires pour livrer un parcours de trading opérationnel.

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

## 📞 Support et communauté

- **Issues GitHub** : Pour signaler des bugs ou proposer des fonctionnalités
- **Discussions** : Pour échanger avec la communauté
- **Documentation** : Guide complet dans le dossier `docs/`

## 📄 Licence

Ce projet est sous licence MIT - voir le fichier `LICENSE` pour plus de détails.

---

> **Développé avec ❤️ par decarvalhoe et la communauté open-source**
> Dernière mise à jour : Novembre 2025
