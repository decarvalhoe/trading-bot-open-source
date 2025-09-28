# Observabilité des KPI

Ce dossier centralise le tableau de bord consolidé des indicateurs clés du programme trading bot.

- `kpi-config.toml` contient la configuration des KPI (cible, propriétaire, mode de mise à jour).
- `kpi-dashboard.md` est généré automatiquement par la CI à chaque run de la _workflow_ `metrics-dashboard.yml`.
- `kpi-dashboard.json` expose la même information sous forme machine (consommable par un outil BI).

## Mise à jour automatique

Le script [`scripts/metrics/build_dashboard.py`](../../scripts/metrics/build_dashboard.py) agrège les résultats de couverture (`coverage.xml`),
les statuts des scénarios E2E et les KPI manuels pour publier le tableau de bord. Il est exécuté par la CI avec les options suivantes :

```bash
python scripts/metrics/build_dashboard.py \
  --config docs/metrics/kpi-config.toml \
  --coverage-xml coverage.xml \
  --test-outcome "$TEST_STATUS" \
  --e2e-log reports/e2e.log \
  --e2e-outcome "$E2E_STATUS" \
  --output-md docs/metrics/kpi-dashboard.md \
  --output-json docs/metrics/kpi-dashboard.json
```

Les artefacts `kpi-dashboard.md` et `kpi-dashboard.json` sont publiés automatiquement dans GitHub Actions pour être consommés
dans un outil BI (Metabase, Power BI, ...).

## Mise à jour manuelle

Les KPI `onboarding`, `mvp_strategy` et `community` restent mis à jour manuellement. Les responsables identifiés renseignent
les nouvelles valeurs dans `kpi-config.toml` lors du comité KPI décrit dans `../governance/kpi-review.md`.
