# Gestion des identifiants brokers chiffrés

Les endpoints `/users/me/broker-credentials` du service **user-service** permettent désormais de stocker les clés API des brokers après chiffrement côté serveur. Cette page décrit la marche à suivre pour activer la fonctionnalité en environnement de déploiement.

## Génération de la clé d'encryption

La clé attendue est une clé [Fernet](https://cryptography.io/en/latest/fernet/) encodée en Base64. Pour en générer une nouvelle :

```bash
python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode("utf-8"))
PY
```

Conservez la valeur générée dans votre coffre de secrets (Vault, Doppler, AWS Secrets Manager, …) sous l'identifiant `BROKER_CREDENTIALS_ENCRYPTION_KEY`.

## Provisionnement dans les environnements

1. **Secret manager** : ajoutez la clé `BROKER_CREDENTIALS_ENCRYPTION_KEY` au coffre utilisé par le déploiement (`SECRET_MANAGER_PROVIDER`).
2. **Configuration runtime** :
   - Sur les environnements orchestrés (`docker-compose`, Kubernetes), exposez la variable d'environnement `BROKER_CREDENTIALS_ENCRYPTION_KEY` pour le conteneur `user_service`.
   - Pour le développement local, ajoutez la clé à `.env.dev` ou laissez `scripts/dev/start.sh` générer une clé éphémère.
3. **Redémarrage** : redémarrez `user-service` après mise à jour afin que la clé soit lue et mise en cache.

## Droits et entitlements nécessaires

L'accès aux endpoints `/users/me/broker-credentials` reste soumis au middleware d'entitlements du service. Les utilisateurs doivent disposer de la capacité `can.use_users` (capabilité par défaut du dashboard). Les opérateurs qui gèrent des identifiants pour d'autres comptes doivent en plus conserver l'entitlement `can.manage_users`.

## Vérifications post-déploiement

- Vérifier que `GET /users/me/broker-credentials` retourne `200` avec `credentials: []` pour un utilisateur nouvellement créé.
- Ajouter une clé via le dashboard web (`/account`) et confirmer que la table `user_broker_credentials` contient des valeurs chiffrées (non lisibles en clair).
- Surveiller les logs du service (`broker credentials encryption key misconfigured`) qui signaleraient une clé manquante ou invalide.
