# Comité de revue KPI

Cette procédure encadre la revue périodique des KPI décrits dans `../metrics/kpi-dashboard.md`.

## Fréquence

- **Hebdomadaire (lundi 14h)** : focus sur l'onboarding, la couverture, le taux E2E et l'avancement MVP.
- **Mensuel (premier lundi du mois)** : revue communautaire élargie avec l'équipe community.

## Participants et responsabilités

| Rôle | Responsable | KPI suivis | Responsabilités |
| ---- | ----------- | ---------- | ---------------- |
| Head of Product | Alice Martin | Onboarding | Consolidation des métriques produit, identification des points de friction et plan d'action. |
| QA Lead | Bruno Silva | Taux de réussite E2E | Validation des scénarios critiques, création de tickets en cas d'échec. |
| Engineering Manager | Chloé Bernard | Couverture de tests | Pilotage de la dette de tests, priorisation des améliorations automatisées. |
| Product Strategy | Diego Lopez | Stratégie MVP | Synchronisation roadmap, arbitrages de scope. |
| Community Lead | Emma Rossi | Communauté | Rapport sur l'engagement Discord/GitHub, plan d'activation. |
| PMO (facilitateur) | Farah Ndiaye | Tous | Animation du comité, mise à jour du plan d'actions et diffusion du compte-rendu. |

## Ordre du jour type

1. Revue des alertes CI (_workflow_ `metrics-dashboard.yml` et artefacts associés).
2. Lecture rapide de la synthèse du tableau de bord KPI.
3. Focus par KPI (max. 5 minutes chacun) :
   - état actuel vs cible,
   - décisions / actions à prendre,
   - responsable et échéance.
4. Validation / mise à jour des valeurs manuelles dans `kpi-config.toml`.
5. Publication du compte-rendu dans l'espace Confluence interne.

## Règles de mise à jour

- Les valeurs automatiques (couverture, taux E2E) ne doivent pas être modifiées manuellement.
- Toute modification du fichier `kpi-config.toml` doit faire l'objet d'une PR dédiée et être approuvée par le PMO.
- Les artefacts CI sont conservés 30 jours et servent de source de vérité pour l'historique.
