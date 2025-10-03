import asyncio

import httpx

from services.market_data.adapters.topstep import TopStepAdapter


class _TransportState:
    def __init__(self) -> None:
        self.calls: list[tuple[str, httpx.Request]] = []
        self.token_requests = 0


def _build_transport(state: _TransportState) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        state.calls.append((request.method, request))
        if request.url.path == "/oauth/token":
            state.token_requests += 1
            return httpx.Response(200, json={"access_token": "token-1", "expires_in": 60})

        auth = request.headers.get("Authorization")
        if auth != "Bearer token-1":
            return httpx.Response(401, json={"detail": "unauthorized"})

        if request.url.path.endswith("/metrics"):
            return httpx.Response(200, json={"balance": 1000})
        if request.url.path.endswith("/performance"):
            params = dict(request.url.params)
            return httpx.Response(200, json={"pnl": [params]})
        if request.url.path.endswith("/risk-rules"):
            return httpx.Response(200, json={"max_drawdown": 100})

        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_topstep_adapter_authenticates_and_fetches_metrics() -> None:
    state = _TransportState()
    client = httpx.AsyncClient(base_url="https://topstep.local", transport=_build_transport(state))
    adapter = TopStepAdapter(
        base_url="https://topstep.local",
        client_id="abc",
        client_secret="def",
        http_client=client,
    )

    async def run() -> None:
        metrics = await adapter.get_account_metrics("acct-1")
        assert metrics == {"balance": 1000}
        await adapter.aclose()

    asyncio.run(run())

    assert state.token_requests == 1
    assert any(path.endswith("/metrics") for _, path in [(m, req.url.path) for m, req in state.calls])


def test_topstep_adapter_reuses_token_until_expiry_and_passes_params() -> None:
    state = _TransportState()

    def handler(request: httpx.Request) -> httpx.Response:
        state.calls.append((request.method, request))
        if request.url.path == "/oauth/token":
            state.token_requests += 1
            token = f"token-{state.token_requests}"
            return httpx.Response(200, json={"access_token": token, "expires_in": 1})

        auth = request.headers.get("Authorization")
        if auth != f"Bearer token-{state.token_requests}":
            return httpx.Response(401, json={"detail": "unauthorized"})

        if request.url.path.endswith("/performance"):
            params = dict(request.url.params)
            return httpx.Response(200, json={"pnl": params})
        if request.url.path.endswith("/risk-rules"):
            return httpx.Response(200, json={"max_daily_loss": 50})
        return httpx.Response(404)

    client = httpx.AsyncClient(
        base_url="https://topstep.local",
        transport=httpx.MockTransport(handler),
    )

    adapter = TopStepAdapter(
        base_url="https://topstep.local",
        client_id="abc",
        client_secret="def",
        http_client=client,
    )

    async def run() -> None:
        history = await adapter.get_performance_history(
            "acct-1", start="2024-01-01", end="2024-02-01"
        )
        await asyncio.sleep(1.1)
        rules = await adapter.get_risk_rules("acct-1")
        assert history == {"pnl": {"start": "2024-01-01", "end": "2024-02-01"}}
        assert rules == {"max_daily_loss": 50}
        await adapter.aclose()

    asyncio.run(run())

    # Token should be refreshed due to expiry before second request
    assert state.token_requests == 2

