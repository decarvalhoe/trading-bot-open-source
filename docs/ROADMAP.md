# Feuille de route 2025 → 2026

Cette feuille de route est alignée sur la revue de code de novembre 2025. Elle met en avant les
jalons trimestriels permettant de livrer un parcours de trading complet et observable.

| Trimestre | Version cible | Fenêtre | Objectifs clés |
|-----------|---------------|---------|----------------|
| T4 2025   | v0.4.0        | Déc. 2025 | Parcours utilisateur complet (auth + profils + TOTP), documentation OpenAPI, backlog de tests contractuels lancé. |
| T1 2026   | v0.5.0        | Mars 2026 | MVP trading sandbox : persistance des stratégies/ordres, CLI de démonstration, rapport Prometheus/Grafana publié. |
| T2 2026   | v0.6.0        | Juin 2026 | Connecteurs marchés priorisés (Binance, IBKR), moteur de risque enrichi, reporting quotidien automatisé. |
| T4 2026   | v1.0.0        | Nov. 2026 | Release publique stable : gouvernance open-source complète, automatisation secrets, tableau de bord web minimal. |

## Gouvernance et suivi

- Le comité roadmap (product, engineering, community) se réunit au démarrage de chaque trimestre pour
  valider la portée, ajuster les dépendances et publier le backlog associé (`docs/tasks/2025-q4-backlog.md`).
- Chaque jalon majeur doit être accompagné d'une documentation mise à jour (`docs/`, README) et d'une
  checklist de tests (unitaires, contractuels, E2E).
- Les métriques clés (taux E2E, couverture, temps d'onboarding) sont revues lors du comité KPI hebdomadaire
  décrit dans `docs/governance/kpi-review.md`.
