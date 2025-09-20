# Trading Bot Open Source

Un projet de bot de trading open-source, construit avec une architecture de microservices moderne.

## Statut du Projet

- **Sprint 1 (Terminé)** : Infrastructure, fondations, CI/CD, et service de configuration.
- **Sprint 2 (En cours)** : Authentification, gestion des utilisateurs, et migrations de base de données.

## Démarrage Rapide (Développement)

```bash
# 1. Installer les dépendances et configurer l'environnement
make setup

# 2. Démarrer l'environnement de développement
make dev-up

# 3. Vérifier que les services fonctionnent
curl http://localhost:8000/health  # config-service
curl http://localhost:8011/health  # auth-service (après TICKET-004)

# 4. Arrêter l'environnement
make dev-down
```

## Architecture

- **`services/`** : Contient les microservices (FastAPI).
  - `config-service` : Gère la configuration centralisée.
  - `auth-service` : Gère l'authentification et les tokens JWT.
  - `user-service` : Gère les profils utilisateurs.
- **`infra/`** : Gère l'infrastructure (Docker, migrations Alembic).
- **`libs/`** : Bibliothèques partagées entre les services.

## Roadmap des Sprints

### Sprint 1 (Terminé)

- **TICKET-001** : Repository, templates, et CI minimal ✅
- **TICKET-002** : Environnement Docker + Compose ✅
- **TICKET-003** : Config-service avec Pydantic + API ✅

### Sprint 2 (En cours)

- **TICKET-004** : Auth-service - Inscription et Connexion des Utilisateurs
- **TICKET-005** : User-service - Gestion des Profils Utilisateurs (CRUD)
- **TICKET-006** : Infrastructure - Migrations de Base de Données avec Alembic

## Contribution

Consultez `CONTRIBUTING.md` pour plus de détails sur la manière de contribuer au projet.

---

> Auteur: Manus AI — Date: 20 janvier 2025 — Version: 2.0
