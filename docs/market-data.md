# Market data service

The `services/market_data` package implements a FastAPI service and background
workers responsible for ingesting, normalising and persisting real-time and
historical market data.

## Service layout

```
services/market_data/
├── adapters/            # Exchange and transport integrations
├── app/                 # FastAPI application, persistence helpers
├── workers/             # Long running collectors and pipelines
└── tests/               # Pytest suite for adapter logic
```

### External adapters

* **Binance** – Production-ready (GA). `adapters/binance.py` wraps the official
  [`binance-connector`](https://pypi.org/project/binance-connector/) REST and
  WebSocket clients with coroutine helpers, retry/backoff and rate limiting.
* **Interactive Brokers (IBKR)** – Production-ready (GA). `adapters/ibkr.py`
  relies on [`ib-async`](https://pypi.org/project/ib-async/) for historical data
  and live ticks with automatic throttling and reconnects.
* **Sierra Chart DTC (stub)** – Experimental. `adapters/dtc.py` currently
  exposes placeholder methods to establish sessions and push batches of ticks;
  replace them once the binary protocol integration starts.

### Persistence pipeline

The service stores market data in PostgreSQL/TimescaleDB hypertables created via
Alembic migrations:

* `market_data_ohlcv` – OHLCV bars keyed by `(exchange, symbol, interval,
  timestamp)` and stored as a hypertable on the `timestamp` column.
* `market_data_ticks` – tick level events keyed by `(exchange, symbol,
  timestamp, source)` and stored as a hypertable on the `timestamp` column.

Helper utilities in `app/persistence.py` convert payloads produced by the
collectors into `INSERT ... ON CONFLICT` statements to keep the dataset idempotent.

### FastAPI application

The FastAPI app exposes:

* `GET /health` – readiness endpoint.
* `POST /webhooks/tradingview` – TradingView webhook entry point that validates
  an `X-Signature` header using HMAC-SHA256. The payload is persisted as a tick
  originating from `TradingView`.

### Environment variables

| Variable | Description |
| --- | --- |
| `TRADINGVIEW_HMAC_SECRET` | Shared secret for TradingView webhook signatures. |
| `MARKET_DATA_DATABASE_URL` | PostgreSQL/TimescaleDB connection string. |
| `BINANCE_API_KEY` / `BINANCE_API_SECRET` | Optional API credentials used by the Binance adapter. |
| `IBKR_HOST` / `IBKR_PORT` / `IBKR_CLIENT_ID` | Connection parameters for the IBKR gateway. |
| `PROVIDERS_SANDBOX_MODE` | Controls the integration tests: keep `sandbox` (default) for mocked APIs or set to `official` to hit the real exchanges. |
| `BINANCE_API_BASE_URL` | Optional override for the Binance REST base URL used by integration tests. |
| `IBKR_HTTP_SANDBOX_URL` | Optional override for the mock IBKR HTTP gateway used by integration tests. |

TimescaleDB must be available with the `timescaledb` extension enabled. Apply
migrations using Alembic from the `infra/` package before starting the service:

```
cd infra
alembic upgrade head
```

Run the service locally with:

```
uvicorn services.market_data.app.main:app --reload
```

### Testing

The adapter layer is covered by asyncio-based tests using mocked REST and
WebSocket clients. Execute the suite from the project root:

```
pytest services/market_data/tests
```

Integration scenarios that exercise the real exchange clients live in
`tests/integration`. They rely on `respx` to emulate the Binance and IBKR
APIs by default and can be pointed to the official endpoints by exporting
`PROVIDERS_SANDBOX_MODE=official` along with the corresponding credentials.
