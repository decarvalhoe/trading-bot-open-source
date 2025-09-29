import asyncio
import importlib.util
import os
import sys
import types
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

os.environ.setdefault("ENTITLEMENTS_BYPASS", "1")

prometheus_stub = types.ModuleType("prometheus_client")


class _DummyMetric:
    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401 - mimic Prometheus signature
        """No-op metric"""

    def labels(self, *args: Any, **kwargs: Any) -> "_DummyMetric":
        return self

    def inc(self, *args: Any, **kwargs: Any) -> None:
        return None

    def observe(self, *args: Any, **kwargs: Any) -> None:
        return None


def _generate_latest() -> bytes:
    return b""


prometheus_stub.CONTENT_TYPE_LATEST = "text/plain"
prometheus_stub.Counter = _DummyMetric
prometheus_stub.Histogram = _DummyMetric
prometheus_stub.generate_latest = _generate_latest  # type: ignore[assignment]
sys.modules.setdefault("prometheus_client", prometheus_stub)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _load_package(alias: str, path: Path) -> None:
    spec = importlib.util.spec_from_file_location(alias, path / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    module.__path__ = [str(path)]  # type: ignore[attr-defined]
    sys.modules[alias] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[attr-defined]


def _load_main_module() -> types.ModuleType:
    _load_package("algo_engine", PACKAGE_ROOT)
    _load_package("algo_engine.app", PACKAGE_ROOT / "app")
    _load_package("algo_engine.app.strategies", PACKAGE_ROOT / "app" / "strategies")
    main_spec = importlib.util.spec_from_file_location(
        "algo_engine.app.main", PACKAGE_ROOT / "app" / "main.py"
    )
    main_module = importlib.util.module_from_spec(main_spec)
    sys.modules["algo_engine.app.main"] = main_module
    assert main_spec and main_spec.loader
    main_spec.loader.exec_module(main_module)  # type: ignore[attr-defined]
    return main_module


MAIN_MODULE = _load_main_module()
DEFAULT_ORDER_ROUTER_CLIENT = MAIN_MODULE.order_router_client


@pytest.fixture(scope="session")
def main_module() -> types.ModuleType:
    return MAIN_MODULE


@pytest.fixture(autouse=True)
def reset_state(main_module: types.ModuleType) -> None:
    store = main_module.store
    orchestrator = main_module.orchestrator
    store._strategies.clear()  # type: ignore[attr-defined]
    orchestrator.update_daily_limit(trades_submitted=0)
    orchestrator.set_mode("paper")
    orchestrator._state.last_simulation = None  # type: ignore[attr-defined]
    orchestrator._state.recent_executions.clear()  # type: ignore[attr-defined]
    orchestrator.set_order_router_client(DEFAULT_ORDER_ROUTER_CLIENT)


class MockRouterController:
    def __init__(self, orchestrator: Any, order_router_factory: Callable[[httpx.AsyncClient], Any]) -> None:
        self._orchestrator = orchestrator
        self._factory = order_router_factory
        self._requests: list[httpx.Request] = []
        self._response: dict[str, Any] = {}
        self._status_code: int = 200
        self._exception: Exception | None = None
        self._transport: httpx.MockTransport | None = None
        self._client: httpx.AsyncClient | None = None
        self._apply_default_response()

    @property
    def requests(self) -> list[httpx.Request]:
        return self._requests

    def _apply_default_response(self) -> None:
        self._response = {
            "order_id": "order-1",
            "status": "filled",
            "broker": "mock-broker",
            "venue": "binance.spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": 1.0,
            "filled_quantity": 1.0,
            "avg_price": 25000.0,
            "submitted_at": "2024-01-01T00:00:00+00:00",
            "fills": [],
            "tags": [],
        }
        self._status_code = 200
        self._exception = None

    def set_response(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._response = payload
        self._status_code = status_code
        self._exception = None

    def set_error(self, exception: Exception) -> None:
        self._exception = exception

    def reset(self) -> None:
        self._requests.clear()
        self._apply_default_response()

    async def _setup(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self._requests.append(request)
            if self._exception is not None:
                raise self._exception
            return httpx.Response(self._status_code, json=self._response)

        self._transport = httpx.MockTransport(handler)
        self._client = httpx.AsyncClient(base_url="http://mock-router", transport=self._transport)
        router_client = self._factory(self._client)
        self._orchestrator.set_order_router_client(router_client)

    async def aclose(self) -> None:
        self._orchestrator.set_order_router_client(DEFAULT_ORDER_ROUTER_CLIENT)
        if self._client is not None:
            await self._client.aclose()
        self._transport = None
        self._client = None


@pytest.fixture
def mock_order_router(main_module: types.ModuleType) -> MockRouterController:
    orchestrator = main_module.orchestrator

    def build_router(async_client: httpx.AsyncClient) -> Any:
        return main_module.OrderRouterClient(client=async_client, base_url="http://mock-router")

    controller = MockRouterController(orchestrator, build_router)
    asyncio.run(controller._setup())
    try:
        yield controller
    finally:
        asyncio.run(controller.aclose())
