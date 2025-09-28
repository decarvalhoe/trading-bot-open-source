# Guide de rotation des clés JWT et TOTP

Ce guide décrit la procédure opérationnelle pour renouveler régulièrement les secrets utilisés par les services `auth-service` et `user-service` afin de signer les JSON Web Tokens (JWT) et générer les graines TOTP. Les rotations fréquentes réduisent la fenêtre d'exploitation en cas d'exposition accidentelle d'un secret.

## Fréquence recommandée

| Secret                         | Fréquence cible | Notes |
| ------------------------------ | --------------- | ----- |
| Clé de signature JWT principale | Tous les 30 jours | Synchroniser la rotation avec les déploiements planifiés. |
| Clé JWT de secours             | Tous les 90 jours | Conserver au moins deux clés actives pour assurer une transition sans coupure. |
| Graines TOTP utilisateur       | Tous les 180 jours | Lancer la régénération lors des campagnes de sécurité ou des ré-initialisations volontaires.

## Préparation

1. Créer une nouvelle clé dans le gestionnaire de secrets (Vault/Doppler/AWS Secrets Manager) sous un identifiant distinct (`JWT_SECRET_v<date>` par exemple).
2. Mettre à jour le mappage `SECRET_MANAGER_KEY_MAPPING` si nécessaire pour que les services puissent récupérer la nouvelle clé.
3. Déployer le secret dans un environnement de pré-production et valider les parcours d'authentification.

## Exécution de la rotation JWT

1. **Phase de chevauchement (24h minimum)**
   - Ajouter la nouvelle clé JWT en tant que clé secondaire dans `auth-service`. Conserver l'ancienne clé comme clé de vérification.
   - Déployer en production et confirmer que les nouveaux tokens utilisent la nouvelle clé.
2. **Phase de retrait**
   - Après expiration du délai d'overlap (>= 24h ou temps de vie maximal des refresh tokens), retirer la clé sortante du gestionnaire de secrets.
   - Invalider les refresh tokens encore actifs si un incident est suspecté.

## Rotation des graines TOTP

1. Préparer une communication aux utilisateurs expliquant la nécessité de regénérer leur double authentification.
2. Activer un flag côté API pour déclencher la régénération (ex: forcer un `reset_required` dans la base).
3. Les utilisateurs enregistrent un nouveau QR code. Anciennes graines désactivées dès que la nouvelle est confirmée.

## Rollback

- **Échec fonctionnel** : remettre le mappage du secret sur la valeur précédente et redéployer. Les tokens signés avec la nouvelle clé deviendront invalides ; communiquer aux clients qu'une reconnexion est nécessaire.
- **Incident utilisateur TOTP** : réactiver temporairement la graine précédente (valable < 24h) puis assister l'utilisateur à regénérer une nouvelle graine.
- Conserver un historique horodaté des clés rotationnées pour permettre une analyse post-mortem.

## Automatisation & audit

- Mettre en place une alerte qui déclenche un ticket si une clé approche sa date d'expiration sans plan de rotation.
- Journaliser chaque accès de lecture aux secrets dans le gestionnaire de secrets et rapprocher ces logs des déploiements.
- Documenter chaque rotation dans le runbook d'exploitation avec la date, l'opérateur et le résultat.
