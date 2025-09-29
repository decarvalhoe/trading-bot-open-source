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
- ✅ **Connecteurs de marché** : Adaptateurs sandbox Binance/IBKR avec limites partagées
- 🔄 **Gestion des ordres** : Persistance et historique d'exécutions en cours d'implémentation

### Phase 4 : Monitoring et Analytics (🔄 En cours - 53%)
**Objectif** : Fournir des outils d'analyse et de suivi des performances

- 🔄 **Service de rapports** (65%) : Calculs de métriques de performance, API et tests unitaires
- 🔄 **Service de notifications** (45%) : Dispatcher, configuration et schémas de données
- 🔄 **Dashboard web** (50%) : Composants React, intégration streaming et affichage des métriques
- 🔄 **Infrastructure d'observabilité** (70%) : Configuration Prometheus/Grafana et dashboard FastAPI

*Prochaines étapes* : Finalisation des services de notification, enrichissement du dashboard web, et configuration des alertes.

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
