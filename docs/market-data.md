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

* **Binance** – `adapters/binance.py` wraps the official
  [`binance-connector`](https://pypi.org/project/binance-connector/) REST and
  WebSocket clients. The adapter exposes coroutine friendly helpers to fetch
  OHLCV bars and to stream live trades with automatic rate limiting and
  reconnection.
* **Interactive Brokers (IBKR)** – `adapters/ibkr.py` uses the
  [`ib-async`](https://pypi.org/project/ib-async/) client to request historical
  data and subscribe to live ticks. The adapter reuses the IBKR throttling
  configuration and reconnects automatically when the gateway disconnects.
* **Sierra Chart DTC (stub)** – `adapters/dtc.py` implements a small stub for
  the Data and Trading Communications protocol. It currently exposes methods to
  establish a session and push batches of ticks; replace these placeholders when
  wiring the real binary protocol.

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
