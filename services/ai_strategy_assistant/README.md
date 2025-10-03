# AI Strategy Assistant

Ce microservice expose une API simple pour transformer une idée de trading en
proposition de stratégie au format YAML ou Python. Il s'appuie sur LangChain et
OpenAI afin de structurer la réponse du modèle et de fournir un résumé,
d'éventuels avertissements ainsi qu'une liste d'indicateurs recommandés.

## Endpoints

| Méthode | Chemin       | Description                                                       |
| ------- | ------------ | ----------------------------------------------------------------- |
| POST    | `/generate`  | Génère un brouillon structuré à partir d'un prompt en langage naturel. |

### Exemple

```bash
curl -X POST http://localhost:8085/generate \
  -H "Content-Type: application/json" \
  -d '{
        "prompt": "Swing trading sur BTC avec confirmation RSI",
        "preferred_format": "yaml",
        "risk_profile": "modéré",
        "indicators": ["RSI", "EMA 20"],
        "notes": "Limiter le drawdown à 10%"
      }'
```

La réponse contient un résumé, le code YAML/Python demandé ainsi que les
métadonnées nécessaires pour alimenter le moteur de stratégies.

## Configuration

Le service attend la variable d'environnement `OPENAI_API_KEY` pour
initialiser `ChatOpenAI`. Pour les tests ou l'environnement de développement,
il est possible d'injecter un LLM factice lors de l'instanciation de
`AIStrategyAssistant`.
