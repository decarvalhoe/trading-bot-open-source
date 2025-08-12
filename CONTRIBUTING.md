# Contribuer

## Branching
- `main`: stable.
- `develop`: intégrations.
- feature branches: `feat/<slug>`, `chore/<slug>`, `fix/<slug>`.

## Commits
- Style recommandé: Conventional Commits (ex: `feat: add risk engine`).
- Lint auto via **pre-commit**.

## Tests & Lint
```bash
pre-commit run -a
pytest -q
```

## PR
- Petite, testée, description claire, checklist CI verte.
