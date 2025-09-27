# Screener Service

Le service **Screener** expose une API REST permettant d'exécuter des screeners actions
sur des fournisseurs tiers (Financial Modeling Prep) et de gérer des presets personnels.

## Exécution d'un screener

```
GET /screener/run
```

Paramètres :

| Nom        | Type      | Description                                                                 |
|------------|-----------|-----------------------------------------------------------------------------|
| `provider` | string    | Provider à utiliser. Seule la valeur `fmp` est supportée pour l'instant.    |
| `limit`    | entier    | Nombre maximum de valeurs retournées (1-200, défaut 50).                    |
| `preset_id`| entier    | Identifiant d'un preset enregistré à réutiliser pour le filtre.             |
| `filters`  | string    | Objet JSON encodé dans la query string décrivant les filtres additionnels.  |

En-têtes requis :

- `x-customer-id` : identifiant numérique de l'utilisateur.

La réponse contient l'identifiant du snapshot créé, les filtres appliqués ainsi que
les résultats bruts retournés par le provider.

## Gestion des presets

Le service permet de gérer des presets utilisateurs, avec suivi des favoris stocké via le
`user-service`. Toutes les opérations requièrent les en-têtes `x-customer-id` et `Authorization`.

### Lister les presets

```
GET /screener/presets
```

Retourne la liste des presets de l'utilisateur courant, avec un indicateur `favorite` basé sur les
préférences récupérées via `user-service`.

### Créer un preset

```
POST /screener/presets
Content-Type: application/json
{
  "name": "Growth",
  "filters": {"marketCapMoreThan": 1000000000},
  "description": "Screener croissance",
  "favorite": true
}
```

- `favorite` optionnel permet d'enregistrer immédiatement le preset comme favori. Le quota
  `limit.watchlists` des entitlements est appliqué.

### Marquer un preset comme favori

```
POST /screener/presets/{preset_id}/favorite
Content-Type: application/json
{
  "favorite": true
}
```

Met à jour la liste des favoris dans `user-service` en respectant le quota `limit.watchlists`.

### Tables persistées

Les tables suivantes sont créées via les migrations Alembic :

- `screener_presets` : définitions des presets utilisateurs.
- `screener_snapshots` : historique des exécutions (filtres appliqués, provider, preset associé).
- `screener_results` : résultats détaillés de chaque snapshot (ordre, score, payload brut).

Chaque exécution `/screener/run` insère un snapshot et les résultats associés.

## Tests

Les tests unitaires du service utilisent des mocks HTTP pour le provider FMP et le `user-service`
afin de vérifier la persistance des snapshots, l'application des quotas de favoris et les mises à jour
de préférences.
