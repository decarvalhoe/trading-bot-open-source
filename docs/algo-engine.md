# Algo Engine Service

Le service **Algo Engine** fournit un registre de stratégies extensible grâce à un système de plugins.

## Plugins de stratégie

- Les classes héritent de `StrategyBase` et définissent un identifiant unique `key`.
- L'enregistrement se fait via le décorateur `@register_strategy`.
- Exemples fournis : `ORBStrategy` (breakout d'ouverture) et `GapFillStrategy` (comblement de gap).

Pour créer un nouveau plugin :

```python
from services.algo_engine.app.strategies import StrategyBase, StrategyConfig, register_strategy

@register_strategy
class MyStrategy(StrategyBase):
    key = "my_strategy"

    def generate_signals(self, market_state: dict) -> list[dict]:
        # logique de signal
        return []
```

## API principale

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/health` | Statut du service |
| GET | `/strategies` | Liste des stratégies et des plugins disponibles |
| POST | `/strategies` | Création d'une stratégie (validation via le registre) |
| POST | `/strategies/generate` | Génération assistée par IA d'un brouillon YAML/Python |
| POST | `/strategies/import` | Import d'une stratégie déclarative YAML ou Python |
| GET | `/strategies/{id}` | Consultation d'une stratégie |
| PUT | `/strategies/{id}` | Mise à jour (activation, paramètres, tags) |
| DELETE | `/strategies/{id}` | Suppression |
| GET | `/state` | Etat de l'orchestrateur (mode paper/live, limites) |
| PUT | `/state` | Mise à jour des limites et du mode |

### Assistant de stratégie IA (optionnel)

L'endpoint `/strategies/generate` repose sur le microservice `ai-strategy-assistant`
et ses dépendances (`langchain`, `langchain-openai`, `openai`, ...). Ces paquets
sont maintenant déclarés dans `services/algo-engine/requirements.txt` afin que
`pip install -r services/algo-engine/requirements.txt` prépare l'environnement.

Le service reste néanmoins fonctionnel sans ces dépendances. Pour désactiver
explicitement l'assistant, définissez `AI_ASSISTANT_ENABLED=0` avant de lancer
`uvicorn app.main:app`. Dans ce cas, `/strategies/generate` renverra un HTTP 503
indiquant que la fonctionnalité est désactivée.

Le middleware d'entitlements vérifie la capacité `can.manage_strategies` et expose la limite de stratégies actives (`max_active_strategies`). L'orchestrateur interne applique les limites journalières.

## Exemple d'utilisation

```bash
curl -X POST http://localhost:8000/strategies \
  -H 'Content-Type: application/json' \
  -d '{
        "name": "Morning Breakout",
        "strategy_type": "orb",
        "parameters": {"opening_range_minutes": 15},
        "enabled": true
      }'
```
