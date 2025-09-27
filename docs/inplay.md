# In-Play Monitoring UI

Le service `inplay` fournit une API REST et un flux WebSocket permettant à l'interface utilisateur de visualiser en temps réel les setups détectés sur les symboles surveillés.

## Points d'accès

### WebSocket

```
GET /inplay/ws
```

* Accepte la connexion et envoie immédiatement un snapshot de chaque watchlist configurée.
* Chaque mise à jour de setup génère un message JSON au format :

```json
{
  "type": "watchlist.update",
  "payload": {
    "id": "momentum",
    "symbols": [
      {
        "symbol": "AAPL",
        "setups": [
          {
            "strategy": "ORB",
            "entry": 190.5,
            "target": 192.0,
            "stop": 189.5,
            "probability": 0.7,
            "updated_at": "2024-03-19T14:35:00Z"
          }
        ]
      }
    ],
    "updated_at": "2024-03-19T14:35:00Z"
  }
}
```

* Le client peut ignorer les messages entrants (aucune trame bidirectionnelle n'est requise).

### REST

```
GET /inplay/watchlists/{watchlist_id}
```

* Retourne l'état courant de la watchlist (`momentum`, `futures`, etc.).
* Structure équivalente au payload WebSocket.

## Intégration UI

1. **Connexion initiale** : ouvrir le WebSocket sur `/inplay/ws` pour recevoir un snapshot complet dès le chargement de la page.
2. **Mises à jour en direct** : chaque message `watchlist.update` remplace l'état local de la watchlist correspondante.
3. **Fallback** : en cas de reconnection, réinterroger l'endpoint REST pour reconstruire la vue avant de reprendre le flux temps réel.
4. **Gestion des symboles** : les watchlists sont définies côté serveur via la configuration (`INPLAY_WATCHLISTS`). Chaque symbole possède une liste ordonnée de setups (les plus récents en premier).

Ces éléments permettent d'afficher un tableau ou des cartes interactives mettant à jour automatiquement les probabilités, cibles et stops des stratégies (ORB, IB, Gap-Fill, Engulfing).
