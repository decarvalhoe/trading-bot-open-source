# Strategies - Declarative Format & APIs

The algo engine now accepts declarative strategies that can be defined either in YAML (JSON is valid YAML) or in a lightweight Python file. Declarative strategies allow non-developers to describe trading rules that are dynamically evaluated by the engine and can be simulated before being promoted to live trading.

## Feature status & prerequisites

| Feature | Status | Activation prerequisites |
| --- | --- | --- |
| Declarative imports | General availability | Available by default via `/strategies/import` |
| Visual Strategy Designer | Beta in the web dashboard | Access `/strategies` route on `web-dashboard`; enable streaming tokens |
| AI Strategy Assistant | Opt-in beta | `pip install -r services/algo-engine/requirements.txt` (assistant auto-enabled), `OPENAI_API_KEY`; set `AI_ASSISTANT_ENABLED=0` to disable |
| Backtesting API | General availability | Ensure `data/backtests/` is writable; run via `/strategies/{id}/backtest` |

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

## Strategy Designer (visual editor)

The web dashboard exposes a drag-and-drop designer under `/strategies`. Blocks are
serialised to the declarative schema described above and can be exported as YAML or
Python before being sent to the algo engine via `/strategies/import`. The feature is
currently in **beta**:

- Works best with the streaming stack running (`make demo-up`) so live setups stay in sync.
- Requires the web dashboard service tokens (`WEB_DASHBOARD_*`) to reach `algo-engine`.
- Tutorial: see the internal screencast referenced in `docs/tutorials/README.md`.

Tests live under `services/web-dashboard/src/strategies/designer/__tests__/` and ensure
block validation remains consistent when adding new components.

## AI strategy assistant

The `ai-strategy-assistant` microservice leverages LangChain and OpenAI to transform natural language prompts into declarative or Python strategies. This capability is opt-in and requires the following configuration before calling `/strategies/generate`:

- Install optional dependencies via `pip install -r services/algo-engine/requirements.txt`.
- The assistant starts automatically once those dependencies are present; export `AI_ASSISTANT_ENABLED=0` if you want the algo engine to stay in non-assistant mode.
- Provide a valid `OPENAI_API_KEY` to the assistant microservice.

The algo engine exposes
`POST /strategies/generate` which forwards the request to the assistant and returns a
draft containing:

- a summary of the proposed approach,
- a YAML or Python implementation (or both),
- recommended indicators and caveats,
- metadata such as the suggested strategy name.

The web dashboard embeds an AI assistant card on the strategies page. Users can choose
from predefined prompts, toggle indicator suggestions, review the generated code and
edit it before importing via `POST /strategies/import/assistant`, which proxies the
payload to the algo engine.

> ℹ️ **Runtime requirements** – Installing
> `pip install -r services/algo-engine/requirements.txt` now pulls the optional
> `langchain`, `langchain-openai` and `openai` dependencies needed by the assistant.
> The feature is enabled by default once those packages are available; toggle it via
> the `AI_ASSISTANT_ENABLED` environment flag handled in
> [`services/algo_engine/app/main.py`](../../services/algo_engine/app/main.py). Set
> `AI_ASSISTANT_ENABLED=0` to boot the algo engine without the feature; in that case
> `/strategies/generate` returns HTTP 503 with a clear message.

## Simulation & artefacts

Backtests run through the `/strategies/{id}/backtest` endpoint leverage the new simulation mode. Results are saved inside `data/backtests/`:

- `<strategy>_TIMESTAMP.json` – metrics, equity curve and summary.
- `<strategy>_TIMESTAMP.log` – chronological trade log.

Each backtest updates the orchestrator state with `mode = "simulation"` and exposes the latest summary under `/state` (`last_simulation`).

Make sure the `data/backtests` directory is writable in your deployment target if you want to persist the artefacts. Use the walkthrough in [`docs/tutorials/backtest-sandbox.ipynb`](../tutorials/backtest-sandbox.ipynb) to replay the demo script end-to-end.
