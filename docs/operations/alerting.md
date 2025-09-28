# Procédure d'escalade des alertes FastAPI

Cette procédure couvre les deux alertes Prometheus livrées par défaut :

- **FastAPIHighLatency** (warning) : latence moyenne > 500 ms pendant 5 minutes.
- **FastAPIHighErrorRate** (critical) : taux de réponses 5xx > 5 % pendant 10 minutes.

## 1. Détection

1. Prometheus évalue les règles toutes les 15 s.
2. En cas de déclenchement, un webhook Alertmanager (à configurer selon l'environnement) doit notifier le canal `#trading-alerts` et ouvrir un ticket dans l'outil ITSM.

## 2. Triage initial

| Rôle | Action |
| --- | --- |
| Support N1 | Confirme la réalité de l'alerte via Grafana (dashboard *FastAPI - Vue d'ensemble*). |
| Support N1 | Identifie le service impacté (`labels.service`). |
| Support N1 | Notifie l'astreinte produit (mail + Slack). |

Si la latence diminue et repasse sous le seuil en moins de 5 minutes supplémentaires, clore l'incident en documentant le ticket.

## 3. Escalade

1. **Astreinte Produit (N2)** – délai de réponse attendu : 15 minutes.
   - Analyse les métriques détaillées, compare avec les déploiements récents.
   - Peut déclencher un rollback si une release vient d'avoir lieu.
2. **Equipe SRE (N3)** – à contacter si :
   - l'alerte `FastAPIHighErrorRate` reste active > 15 minutes ;
   - plusieurs services sont impactés simultanément ;
   - le support N2 demande un support infrastructure.
   - Contact : téléphone d'astreinte + e-mail `sre@trading-bot.local`.

## 4. Résolution & post-mortem

- Documenter la cause racine et les actions correctives dans le ticket.
- Programmer un post-mortem si l'alerte critical a duré > 30 minutes ou a généré un impact client.
- Mettre à jour ce document en cas de changement de contacts ou de seuils.
