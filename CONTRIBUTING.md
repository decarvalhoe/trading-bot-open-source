# Contributing Guide

[English](#english-guide) | [Français](#guide-francais)

<a id="english-guide"></a>
## English Guide

Thank you for your interest in Trading Bot Open Source! This guide outlines what we expect from contributors so everyone can collaborate effectively.

### 1. Before You Start

- Read the [Code of Conduct](CODE_OF_CONDUCT.md) and agree to follow it.
- Review the existing issues and roadmap in `docs/project-evaluation.md` to identify current priorities.
- Open an issue if you want to discuss a new feature or major change before you begin coding.

### 2. Set Up Your Environment

```bash
git clone https://github.com/decarvalhoe/trading-bot-open-source.git
cd trading-bot-open-source
make setup           # install development dependencies
make dev-up          # start PostgreSQL, Redis, and core services
```

Consult the `Makefile` and the `docs/` directory for other useful commands (E2E tests, import scripts, etc.).

### 3. Git Strategy

- Use feature branches: `feat/<slug>`, `fix/<slug>`, `chore/<slug>`.
- Keep `main` stable; use `develop` (if available) for intermediate integrations.
- Rebase regularly on `main` to limit conflicts.

### 4. Code Style and Commits

- Follow the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) convention.
- Formatting and quality are enforced by `black`, `isort`, `flake8`, and strict `mypy`.
- Before pushing, run:

```bash
pre-commit run -a
pytest -q            # add tests when you modify or introduce features
make e2e             # optional but recommended to validate the auth flow
```

Document new commands, environment variables, or schemas in `docs/`.

### 5. Submit a Pull Request

1. Ensure tests pass locally and CI runs cleanly.
2. Fill in the PR description with the motivation, implementation details, and potential impacts.
3. Attach screenshots or relevant logs if your change affects the UI or observability.
4. Mention related issues (`Fixes #123`).
5. Be ready to iterate based on review feedback.

### 6. Code Review

- Maintainers validate technical coherence, security, and documentation.
- Feedback must remain respectful and constructive; feel free to ask for clarifications.
- At least two approvals are recommended for significant changes (services, data schemas, infrastructure).

### 7. Non-Code Contributions

Documentation, translations, project management, and testing are equally appreciated. Please surface them via dedicated issues or discussions.

---

<a id="guide-francais"></a>
## Guide français

Merci de votre intérêt pour Trading Bot Open Source ! Ce guide résume les attentes pour contribuer dans les meilleures conditions.

### 1. Avant de commencer

- Lisez le [Code de conduite](CODE_OF_CONDUCT.md) et engagez-vous à le respecter.
- Parcourez les issues existantes et la feuille de route dans `docs/project-evaluation.md` pour identifier les priorités actuelles.
- Ouvrez une issue si vous souhaitez discuter d'une nouvelle fonctionnalité ou d'un changement majeur avant de démarrer le développement.

### 2. Préparer votre environnement

```bash
git clone https://github.com/decarvalhoe/trading-bot-open-source.git
cd trading-bot-open-source
make setup           # installe les dépendances de développement
make dev-up          # lance PostgreSQL, Redis et les services principaux
```

Consultez le `Makefile` et le dossier `docs/` pour d'autres commandes utiles (tests E2E, scripts d'import, etc.).

### 3. Stratégie Git

- Branche par fonctionnalité : `feat/<slug>`, `fix/<slug>`, `chore/<slug>`.
- `main` : branche stable ; `develop` (si existante) pour les intégrations intermédiaires.
- Rebasez-vous régulièrement sur `main` pour limiter les conflits.

### 4. Style de code et commits

- Suivez les conventions [Conventional Commits](https://www.conventionalcommits.org/fr/v1.0.0/).
- Le formatage et la qualité sont automatisés via `black`, `isort`, `flake8` et `mypy` (mode strict).
- Avant de pousser, exécutez :

```bash
pre-commit run -a
pytest -q            # ajoutez des tests lorsqu'une fonctionnalité est modifiée ou introduite
make e2e             # optionnel mais recommandé pour valider le parcours auth
```

Documentez les nouvelles commandes, variables d'environnement ou schémas dans `docs/`.

### 5. Soumettre une Pull Request

1. Vérifiez que les tests passent localement et que la CI s'exécute sans erreur.
2. Remplissez la description en expliquant la motivation, l'implémentation et les impacts éventuels.
3. Ajoutez des captures ou extraits de logs pertinents si votre changement touche l'UI ou l'observabilité.
4. Mentionnez les issues liées (`Fixes #123`).
5. Soyez prêt·e à itérer suite aux retours de revue.

### 6. Revue de code

- Les mainteneurs valident la cohérence technique, la sécurité et la documentation.
- Les retours doivent rester respectueux et constructifs ; n'hésitez pas à poser des questions.
- Un minimum de deux approbations est recommandé pour les changements significatifs (services, schémas de données, infrastructure).

### 7. Contribution non-code

Les contributions sur la documentation, les traductions, la gestion de projet et les tests sont tout autant appréciées. Signalez-les via des issues dédiées ou des discussions.

---

Merci de contribuer à faire de Trading Bot Open Source une plateforme fiable et collaborative !
