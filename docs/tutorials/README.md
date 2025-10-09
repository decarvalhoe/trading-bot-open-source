# Tutorials hub

Updated assets accompanying the December 2025 release refresh. Share these links
with contributors and customer-facing teams.

## Backtest sandbox notebook

- File: [`backtest-sandbox.ipynb`](backtest-sandbox.ipynb)
- Scope: runs `scripts/dev/bootstrap_demo.py` end-to-end against the demo stack,
  inspects `data/backtests/` outputs and demonstrates how to import the generated
  strategy into the algo engine.
- Prerequisites: `pip install -r services/algo-engine/requirements.txt`
  (assistant auto-enabled) and an `OPENAI_API_KEY`; export
  `AI_ASSISTANT_ENABLED=0` if you prefer to keep the assistant disabled while
  following the notebook. See [`services/algo_engine/app/main.py`](../../services/algo_engine/app/main.py)
  for the environment flag logic.

## Strategy designer screencast

- Location: Internal video library → `Trading Bot / 2025-12 Strategy Designer.mp4`
- Highlights the new drag-and-drop blocks, YAML/Python export and import to the
  algo engine.
- Captures the beta limitations and best practices documented in
  `docs/strategies/README.md`.

## Real-time dashboard walkthrough

- Notes: follow `docs/inplay.md` and `docs/streaming.md` to configure service
  tokens, then watch the dashboard pick up live alerts and setups.
- Complementary Grafana board exported under `docs/observability/` for latency
  troubleshooting.
