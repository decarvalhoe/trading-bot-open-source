# Strategies - Declarative Format & APIs

The algo engine now accepts declarative strategies that can be defined either in YAML (JSON is valid YAML) or in a lightweight Python file. Declarative strategies allow non-developers to describe trading rules that are dynamically evaluated by the engine and can be simulated before being promoted to live trading.

## Declarative schema

A declarative strategy definition is a mapping with the following keys:

- `name` (**required**): Human readable strategy name.
- `rules` (**required**): List of rule blocks. Each rule must define:
  - `when`: A condition tree composed of `field`, `operator`, `value` entries or nested `any` / `all` arrays.
  - `signal`: Arbitrary payload describing the action emitted when the condition is true (for example `{"action": "buy", "size": 1}`).
- `parameters` (optional): Additional configuration keys copied into the strategy configuration.
- `metadata` (optional): Arbitrary descriptive attributes stored alongside the strategy.

### YAML example

```yaml
name: Gap Reversal
parameters:
  timeframe: 1h
  risk: medium
rules:
  - when:
      any:
        - { field: close, operator: gt, value: 102 }
        - { field: close, operator: lt, value: 98 }
    signal:
      action: rebalance
      size: 1
metadata:
  author: quant-team
  tags:
    - declarative
```

### Python example

```python
STRATEGY = {
    "name": "Python Breakout",
    "rules": [
        {
            "when": {"field": "close", "operator": "gt", "value": 100},
            "signal": {"action": "buy", "size": 1},
        },
        {
            "when": {"field": "close", "operator": "lt", "value": 95},
            "signal": {"action": "sell", "size": 1},
        },
    ],
    "parameters": {"timeframe": "1h"},
    "metadata": {"created_by": "quantops"},
}
```

Python strategies may alternatively expose a `build_strategy()` function returning the same mapping. The Python loader runs in a restricted namespace with access to basic builtins only.

## API usage

| Endpoint | Method | Description |
| --- | --- | --- |
| `/strategies/import` | `POST` | Import a declarative strategy. Body: `{ "format": "yaml" | "python", "content": "...", "name": "optional override", "tags": [], "enabled": false }`. Returns the created strategy record. |
| `/strategies/{strategy_id}/export?fmt=yaml` | `GET` | Export the original source content for a declarative strategy. The requested format must match the original. |
| `/strategies/{strategy_id}/backtest` | `POST` | Run a simulation for the given strategy. Body: `{ "market_data": [ {"close": 100}, ... ], "initial_balance": 10000 }`. Returns performance metrics and file paths containing logs and equity data. |

Imported strategies are stored with their original source (for re-export) and the evaluated definition under `parameters.definition`.

## Simulation & artefacts

Backtests run through the `/strategies/{id}/backtest` endpoint leverage the new simulation mode. Results are saved inside `data/backtests/`:

- `<strategy>_TIMESTAMP.json` – metrics, equity curve and summary.
- `<strategy>_TIMESTAMP.log` – chronological trade log.

Each backtest updates the orchestrator state with `mode = "simulation"` and exposes the latest summary under `/state` (`last_simulation`).

Make sure the `data/backtests` directory is writable in your deployment target if you want to persist the artefacts.
