# Market Data Service Connectors

This service exposes reusable market data connectors that implement the shared
`MarketConnector` interface from `libs.connectors`. Each connector is
responsible for handling its own rate limiting windows and retry strategies when
communicating with upstream exchanges.

## Rate limiting

* **Binance** – Requests are throttled by an asynchronous sliding-window rate
  limiter. The limiter enforces the `request_rate` over the configured time
  interval before allowing additional REST calls.
* **IBKR** – The connector mirrors Interactive Brokers' native pacing rules by
  deferring requests through the same rate limiter abstraction before issuing
  historical data queries.

## Retries

Both connectors automatically retry websocket subscriptions or market data
requests when they experience transient disconnects:

* The Binance websocket client reopens the stream after temporary connection
  errors and continues streaming once reconnected.
* The IBKR client reconnects to the gateway, resubmits market data subscriptions
  and resumes iteration whenever socket-level errors are raised.

See `services/market_data/tests/test_connector_integration.py` for integration
examples that exercise these behaviours using docker-style fixtures.
