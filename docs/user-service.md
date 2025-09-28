# User Service

Le service **User** centralise les profils applicatifs et expose une API REST sécurisée
par JWT ainsi que le middleware d'entitlements commun.

## Endpoints principaux

### `POST /users/register`
Permet d'inscrire un utilisateur auto-hébergé. L'inscription crée un profil inactif
qui peut ensuite être activé. Exemple de requête (Front) :

```http
POST /users/register HTTP/1.1
Content-Type: application/json

{
  "email": "jane@example.com",
  "display_name": "Jane"
}
```

La réponse contient l'identifiant interne et l'état `is_active=false`.

### `POST /users/{user_id}/activate`
Active un compte (par l'utilisateur ou un opérateur muni de `can.manage_users`).
La requête nécessite :

- un header `Authorization: Bearer <JWT>` où `sub` correspond à `user_id` ;
- `x-customer-id: <user_id>` pour que le middleware attache les entitlements.

Exemple d'appel depuis le front (après génération d'un JWT côté client) :

```http
POST /users/42/activate HTTP/1.1
Authorization: Bearer <token>
x-customer-id: 42
```

### `PATCH /users/{user_id}`
Met à jour le profil (nom complet, langue, consentement marketing). Les champs
sensibles (`email`, `full_name`, `marketing_opt_in`) sont masqués lorsque
l'appelant n'est pas le propriétaire et ne possède pas `can.manage_users`.

```http
PATCH /users/42 HTTP/1.1
Authorization: Bearer <token>
x-customer-id: 42
Content-Type: application/json

{
  "display_name": "Jane Doe",
  "full_name": "Jane Dominique",
  "locale": "fr_FR",
  "marketing_opt_in": true
}
```

### `PUT /users/me/preferences`
Remplace complètement les préférences JSON de l'utilisateur courant.

```http
PUT /users/me/preferences HTTP/1.1
Authorization: Bearer <token>
x-customer-id: 42
Content-Type: application/json

{
  "preferences": {
    "theme": "dark",
    "currency": "EUR"
  }
}
```

La réponse reflète le document sauvegardé.

### `GET /users/{user_id}` et `GET /users`
- `GET /users/{user_id}` retourne un profil avec masquage automatique des champs
  sensibles lorsque l'appelant n'est pas autorisé.
- `GET /users` nécessite `can.manage_users` et renvoie la liste complète pour un
  back-office.

## Flux recommandé (inscription → activation → profil)

1. `POST /users/register` pour créer le compte applicatif.
2. Génération d'un JWT contenant `sub=<user_id>` (depuis l'auth-service ou le
   front en possession du secret durant les tests).
3. `POST /users/{user_id}/activate` pour basculer `is_active` à `true`.
4. `PATCH /users/{user_id}` et `PUT /users/me/preferences` pour renseigner le
   profil et les préférences.

L'OpenAPI générée par FastAPI expose ces exemples directement dans la section
correspondante via les docstrings des endpoints.
