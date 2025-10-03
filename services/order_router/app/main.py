"""Order router service centralising broker connectivity."""
from __future__ import annotations

import asyncio
import logging
import math
import os
import threading
from collections import defaultdict
from concurrent.futures import Future
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

import httpx

from libs.db.db import SessionLocal
from libs.entitlements import install_entitlements_middleware
from libs.observability.logging import RequestContextMiddleware, configure_logging
from libs.observability.metrics import setup_metrics
from libs.portfolio import (
    decode_position_key,
    encode_portfolio_key,
    encode_position_key,
)
from infra.trading_models import Execution as ExecutionModel
from infra.trading_models import Order as OrderModel
from infra.trading_models import SimulatedExecution as SimulatedExecutionModel
from providers.binance import BinanceClient, BinanceConfig
from providers.ibkr import IBKRClient, IBKRConfig
from providers.limits import build_plan, get_pair_limit, iter_supported_pairs
from schemas.market import (
    ExecutionFill,
    ExecutionPlan,
    ExecutionStatus,
    ExecutionVenue,
    OrderSide,
    OrderType,
    TimeInForce,
)
from schemas.order_router import (
    ExecutionIntent,
    ExecutionRecord,
    ExecutionReport,
    ExecutionsMetadata,
    OrderAnnotationPayload,
    OrderRecord,
    OrdersLogMetadata,
    PaginatedExecutions,
    PaginatedOrders,
    PositionCloseRequest,
    PositionCloseResponse,
    PositionHolding,
    PortfolioSnapshot,
    PositionsResponse,
    RiskOverrides,
)
from services.streaming.app.schemas import StreamIngestPayload

from .database import get_session

from .brokers import BinanceAdapter, BrokerAdapter, IBKRAdapter
from .risk_rules import (
    DynamicLimitRule,
    DynamicLimitStore,
    MaxDailyLossRule,
    MaxNotionalRule,
    RiskEngine,
    RiskLevel,
    RiskSignal,
    StopLossRule,
    SymbolLimit,
)


logger = logging.getLogger("order-router.risk")
streaming_logger = logging.getLogger("order-router.streaming")


class Settings(BaseSettings):
    """Runtime configuration sourced from environment variables."""

    binance_api_key: str | None = Field(default=None, alias="BINANCE_API_KEY")
    binance_api_secret: str | None = Field(default=None, alias="BINANCE_API_SECRET")
    binance_api_url: str = Field(default="https://api.binance.com", alias="BINANCE_API_URL")
    binance_recv_window: int = Field(default=5_000, alias="BINANCE_RECV_WINDOW")
    binance_requests_per_minute: int = Field(
        default=1_200, alias="BINANCE_REQUESTS_PER_MINUTE"
    )
    binance_rate_interval_seconds: float = Field(
        default=60.0, alias="BINANCE_RATE_INTERVAL_SECONDS"
    )
    binance_timeout: float = Field(default=10.0, alias="BINANCE_TIMEOUT")
    ibkr_api_key: str | None = Field(default=None, alias="IBKR_API_KEY")
    ibkr_api_secret: str | None = Field(default=None, alias="IBKR_API_SECRET")
    ibkr_api_url: str = Field(default="https://localhost:5000", alias="IBKR_API_URL")
    ibkr_account_id: str | None = Field(default=None, alias="IBKR_ACCOUNT_ID")
    ibkr_requests_per_minute: int = Field(default=60, alias="IBKR_REQUESTS_PER_MINUTE")
    ibkr_rate_interval_seconds: float = Field(default=60.0, alias="IBKR_RATE_INTERVAL_SECONDS")
    ibkr_timeout: float = Field(default=10.0, alias="IBKR_TIMEOUT")


@lru_cache
def get_settings() -> Settings:
    return Settings()


@dataclass
class StreamingConfig:
    ingest_url: str | None
    service_token: str | None
    room_id: str
    timeout: float = 5.0
    max_attempts: int = 3
    backoff_factor: float = 0.5

    @property
    def enabled(self) -> bool:
        return bool(self.ingest_url and self.service_token)

    @classmethod
    def from_env(cls) -> "StreamingConfig":
        return cls(
            ingest_url=os.getenv("STREAMING_INGEST_URL"),
            service_token=os.getenv("STREAMING_SERVICE_TOKEN"),
            room_id=os.getenv("STREAMING_ROOM_ID", "public-room"),
        )


class StreamingIngestClient:
    """Async client responsible for forwarding events to the streaming service."""

    def __init__(self, config: StreamingConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        if config.enabled and config.ingest_url and config.service_token:
            base_url = config.ingest_url.rstrip("/")
            self._client = httpx.AsyncClient(
                base_url=base_url,
                headers={"X-Service-Token": config.service_token},
                timeout=config.timeout,
            )
        self._max_attempts = max(1, config.max_attempts)
        self._backoff_factor = max(0.0, config.backoff_factor)

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        if not self.enabled:
            return
        self._loop = loop

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def publish(self, payload: Dict[str, Any]) -> None:
        if not self._client or not self._loop:
            return
        future: Future[None] = asyncio.run_coroutine_threadsafe(
            self._send_with_retry(payload), self._loop
        )
        future.add_done_callback(self._log_failure)

    async def _send_with_retry(self, payload: Dict[str, Any]) -> None:
        assert self._client is not None  # for mypy
        body = StreamIngestPayload(
            room_id=self._config.room_id,
            source="reports",
            payload=payload,
        ).model_dump()
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._client.post("/ingest/reports", json=body)
                response.raise_for_status()
                return
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500:
                    streaming_logger.warning(
                        "Streaming ingest rejected payload (status=%s)",
                        exc.response.status_code,
                    )
                    return
                last_error = exc
            except httpx.RequestError as exc:
                last_error = exc
            if attempt < self._max_attempts:
                await asyncio.sleep(self._backoff_factor * attempt)
        if last_error is not None:
            streaming_logger.error(
                "Unable to forward streaming payload after %s attempts",
                self._max_attempts,
                exc_info=last_error,
            )

    @staticmethod
    def _log_failure(future: Future[None]) -> None:
        try:
            future.result()
        except Exception as exc:  # pragma: no cover - background logging
            streaming_logger.warning("Streaming ingest task failed", exc_info=exc)


class OrderEventsPublisher:
    def order_persisted(
        self, order: ExecutionIntent, report: ExecutionReport, account_id: str
    ) -> None:
        raise NotImplementedError

    def order_cancelled(self, order: OrderModel, report: ExecutionReport) -> None:
        raise NotImplementedError

    def simulated_execution(
        self, order: ExecutionIntent, report: ExecutionReport, account_id: str
    ) -> None:
        raise NotImplementedError


class NullOrderEventsPublisher(OrderEventsPublisher):
    def order_persisted(
        self, order: ExecutionIntent, report: ExecutionReport, account_id: str
    ) -> None:  # pragma: no cover - intentional no-op
        return

    def order_cancelled(self, order: OrderModel, report: ExecutionReport) -> None:  # pragma: no cover - intentional no-op
        return

    def simulated_execution(
        self, order: ExecutionIntent, report: ExecutionReport, account_id: str
    ) -> None:  # pragma: no cover - intentional no-op
        return


class PortfolioAggregator:
    """Maintain per-account positions derived from executions."""

    _EPSILON = 1e-9

    def __init__(self) -> None:
        self._positions: dict[str, dict[str, dict[str, float]]] = defaultdict(
            lambda: defaultdict(
                lambda: {
                    "net_quantity": 0.0,
                    "abs_quantity": 0.0,
                    "abs_notional": 0.0,
                    "last_price": 0.0,
                }
            )
        )

    @staticmethod
    def _normalise_account(account_id: str | None) -> str:
        cleaned = (account_id or "").strip()
        return cleaned or "default"

    @staticmethod
    def _normalise_symbol(symbol: str | None) -> str:
        return (symbol or "").strip()

    @staticmethod
    def _format_account_label(account_id: str) -> str:
        normalised = account_id.replace("_", " ").replace("-", " ")
        words = [segment for segment in normalised.split(" ") if segment]
        if not words:
            return account_id or "Portefeuille"
        return " ".join(word.capitalize() for word in words)

    @staticmethod
    def _direction(side: str | OrderSide | None) -> float:
        if isinstance(side, OrderSide):
            value = side.value
        else:
            value = str(side or "buy")
        return -1.0 if value.lower().startswith("s") else 1.0

    def reset(self) -> None:
        self._positions.clear()

    def apply_fill(
        self,
        *,
        account_id: str | None,
        symbol: str | None,
        side: str | OrderSide | None,
        quantity: float,
        price: float | None,
    ) -> bool:
        symbol_key = self._normalise_symbol(symbol)
        if not symbol_key:
            return False
        if quantity <= 0:
            return False
        price_value = float(price or 0.0)
        if price_value <= 0:
            return False
        account_key = self._normalise_account(account_id)
        direction = self._direction(side)
        stats = self._positions[account_key][symbol_key]
        stats["net_quantity"] += quantity * direction
        stats["abs_quantity"] += quantity
        stats["abs_notional"] += quantity * price_value
        stats["last_price"] = price_value
        return True

    def apply_report(self, report: ExecutionReport, account_id: str) -> bool:
        applied = False
        for fill in report.fills:
            applied |= self.apply_fill(
                account_id=account_id,
                symbol=report.symbol,
                side=report.side,
                quantity=float(fill.quantity),
                price=float(fill.price),
            )
        if not applied and report.filled_quantity > 0:
            applied = self.apply_fill(
                account_id=account_id,
                symbol=report.symbol,
                side=report.side,
                quantity=float(report.filled_quantity),
                price=float(report.avg_price or 0.0),
            )
        return applied

    def snapshot(self) -> List[Dict[str, Any]]:
        portfolios: List[Dict[str, Any]] = []
        for account_id, symbols in sorted(self._positions.items(), key=lambda item: item[0]):
            holdings: List[Dict[str, Any]] = []
            total_value = 0.0
            portfolio_id = encode_portfolio_key(account_id)
            for symbol, stats in sorted(symbols.items(), key=lambda item: item[0]):
                net_quantity = stats["net_quantity"]
                if math.isclose(net_quantity, 0.0, abs_tol=self._EPSILON):
                    continue
                if math.isclose(stats["abs_quantity"], 0.0, abs_tol=self._EPSILON):
                    continue
                average_price = stats["abs_notional"] / stats["abs_quantity"]
                last_price = stats["last_price"] or average_price or 0.0
                market_value = net_quantity * last_price
                holding = {
                    "id": encode_position_key(account_id, symbol),
                    "portfolio_id": portfolio_id,
                    "portfolio": account_id,
                    "account_id": account_id,
                    "symbol": symbol,
                    "quantity": float(net_quantity),
                    "average_price": float(average_price or 0.0),
                    "current_price": float(last_price or 0.0),
                    "market_value": float(market_value),
                }
                holdings.append(holding)
                total_value += float(market_value)
            if holdings:
                portfolios.append(
                    {
                        "id": portfolio_id,
                        "name": self._format_account_label(account_id),
                        "owner": account_id,
                        "holdings": holdings,
                        "total_value": float(total_value),
                    }
                )
        return portfolios


def rebuild_positions_snapshot(
    session: Session, aggregator: PortfolioAggregator | None = None
) -> List[Dict[str, Any]]:
    """Rebuild an aggregated snapshot of all positions from persisted orders."""

    target = aggregator or PortfolioAggregator()
    target.reset()
    statement = (
        select(OrderModel)
        .options(selectinload(OrderModel.executions))
        .order_by(OrderModel.created_at.asc())
    )
    result = session.execute(statement).unique()
    orders = list(result.scalars().all())
    for order in orders:
        side = order.side
        account_id = order.account_id
        for execution in sorted(order.executions, key=lambda item: item.executed_at):
            quantity = float(execution.quantity or 0.0)
            price = float(execution.price or 0.0)
            if quantity <= 0 or price <= 0:
                continue
            target.apply_fill(
                account_id=account_id,
                symbol=order.symbol,
                side=side,
                quantity=quantity,
                price=price,
            )
    return target.snapshot()


def rebuild_simulated_snapshot(
    session: Session, aggregator: PortfolioAggregator | None = None
) -> List[Dict[str, Any]]:
    """Rebuild an aggregated snapshot using simulated executions only."""

    target = aggregator or PortfolioAggregator()
    target.reset()
    statement = select(SimulatedExecutionModel).order_by(
        SimulatedExecutionModel.submitted_at.asc(),
        SimulatedExecutionModel.created_at.asc(),
    )
    executions = session.execute(statement).scalars().all()
    for execution in executions:
        quantity = float(execution.filled_quantity or execution.quantity or 0.0)
        price = float(execution.price or 0.0)
        if quantity <= 0 or price <= 0:
            continue
        target.apply_fill(
            account_id=execution.account_id,
            symbol=execution.symbol,
            side=execution.side,
            quantity=quantity,
            price=price,
        )
    return target.snapshot()


def build_positions_response(session: Session) -> PositionsResponse:
    """Return a strongly typed response describing the current positions."""

    mode = router.current_mode()
    if mode == "dry_run":
        snapshot = rebuild_simulated_snapshot(session)
    else:
        snapshot = rebuild_positions_snapshot(session)
    items = [PortfolioSnapshot.model_validate(item) for item in snapshot]
    return PositionsResponse(items=items, as_of=datetime.now(timezone.utc))


class StreamingOrderEventsPublisher(OrderEventsPublisher):
    def __init__(self, client: StreamingIngestClient | None) -> None:
        self._client = client
        self._aggregator = PortfolioAggregator()
        self._simulated_aggregator = PortfolioAggregator()

    def order_persisted(
        self, order: ExecutionIntent, report: ExecutionReport, account_id: str
    ) -> None:
        if not self._client or not self._client.enabled:
            return
        aggregated = False
        if report.filled_quantity > 0:
            transaction = self._build_transaction(
                order, report, account_id, mode="live"
            )
            self._client.publish({"resource": "transactions", "items": [transaction]})
            aggregated = self._aggregator.apply_report(report, account_id)
        log_entry = self._build_log_entry(
            timestamp=report.submitted_at,
            status=report.status.value,
            symbol=report.symbol,
            order_id=report.order_id,
            tags=report.tags or order.tags,
            broker=order.broker,
            side=order.side.value,
            account_id=account_id,
            quantity=report.quantity,
            filled_quantity=report.filled_quantity,
            avg_price=report.avg_price or order.price,
            mode="live",
        )
        self._client.publish({"resource": "logs", "entry": log_entry})
        if aggregated:
            self._publish_portfolios(mode="live")

    def order_cancelled(self, order: OrderModel, report: ExecutionReport) -> None:
        if not self._client or not self._client.enabled:
            return
        log_entry = self._build_log_entry(
            timestamp=report.submitted_at,
            status=report.status.value,
            symbol=report.symbol,
            order_id=report.order_id,
            tags=report.tags,
            broker=order.broker,
            side=order.side,
            account_id=order.account_id,
            quantity=float(order.quantity or 0),
            filled_quantity=float(order.filled_quantity or Decimal("0")),
            avg_price=report.avg_price,
            mode="live",
        )
        self._client.publish({"resource": "logs", "entry": log_entry})

    def reload_state(self, session: Session) -> None:
        if not self._client or not self._client.enabled:
            return
        snapshot = rebuild_positions_snapshot(session, self._aggregator)
        self._publish_portfolios(snapshot, mode="live")
        simulated_snapshot = rebuild_simulated_snapshot(
            session, self._simulated_aggregator
        )
        if simulated_snapshot:
            self._publish_portfolios(simulated_snapshot, mode="dry_run")

    def simulated_execution(
        self, order: ExecutionIntent, report: ExecutionReport, account_id: str
    ) -> None:
        if not self._client or not self._client.enabled:
            return
        aggregated = False
        if report.filled_quantity > 0:
            transaction = self._build_transaction(
                order, report, account_id, mode="dry_run"
            )
            transaction["simulated"] = True
            self._client.publish({"resource": "transactions", "items": [transaction]})
            aggregated = self._simulated_aggregator.apply_report(report, account_id)
        log_entry = self._build_log_entry(
            timestamp=report.submitted_at,
            status=report.status.value,
            symbol=report.symbol,
            order_id=report.order_id,
            tags=report.tags or order.tags,
            broker=order.broker,
            side=order.side.value,
            account_id=account_id,
            quantity=report.quantity,
            filled_quantity=report.filled_quantity,
            avg_price=report.avg_price or order.price,
            mode="dry_run",
            simulated=True,
        )
        self._client.publish({"resource": "logs", "entry": log_entry})
        if aggregated:
            self._publish_portfolios(mode="dry_run")

    def _publish_portfolios(
        self, snapshot: Optional[List[Dict[str, Any]]] = None, *, mode: str = "live"
    ) -> None:
        if not self._client or not self._client.enabled:
            return
        if mode == "dry_run":
            aggregator = self._simulated_aggregator
        else:
            aggregator = self._aggregator
        items = snapshot if snapshot is not None else aggregator.snapshot()
        payload = {
            "resource": "portfolios",
            "items": items,
            "mode": mode,
            "type": "positions",
        }
        self._client.publish(payload)

    @staticmethod
    def _normalise_timestamp(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.isoformat()

    def _build_transaction(
        self,
        order: ExecutionIntent,
        report: ExecutionReport,
        account_id: str,
        *,
        mode: str = "live",
    ) -> Dict[str, Any]:
        price = report.avg_price or order.price or 0.0
        transaction = {
            "timestamp": self._normalise_timestamp(report.submitted_at),
            "portfolio": account_id,
            "symbol": report.symbol,
            "side": order.side.value,
            "quantity": report.filled_quantity,
            "price": price,
            "mode": mode,
        }
        if mode != "live":
            transaction["simulated"] = True
        return transaction

    def _build_log_entry(
        self,
        *,
        timestamp: datetime,
        status: str,
        symbol: str,
        order_id: str,
        tags: Optional[List[str]],
        broker: str,
        side: str | None,
        account_id: str | None,
        quantity: float | Decimal | None,
        filled_quantity: float | Decimal | None,
        avg_price: float | Decimal | None,
        mode: str = "live",
        simulated: bool = False,
    ) -> Dict[str, Any]:
        status_text = status.upper()
        if simulated or mode != "live":
            status_text = f"SIMULATED {status_text}"
        message_parts = [status_text, symbol]
        if order_id:
            message_parts.append(f"(ordre {order_id})")
        entry: Dict[str, Any] = {
            "timestamp": self._normalise_timestamp(timestamp),
            "message": " ".join(part for part in message_parts if part),
            "status": status_text,
            "symbol": symbol,
            "order_id": order_id,
            "mode": mode,
        }
        if simulated or mode != "live":
            entry["simulated"] = True
        strategy_hint = self._extract_strategy_hint(tags)
        if strategy_hint:
            entry["strategy_hint"] = strategy_hint
        extra: Dict[str, Any] = {}
        if broker:
            extra["broker"] = broker
        if side:
            extra["side"] = side
        if account_id:
            extra["account_id"] = account_id
        if quantity is not None:
            extra["quantity"] = float(quantity)
        if filled_quantity is not None:
            extra["filled_quantity"] = float(filled_quantity)
        if avg_price is not None:
            extra["avg_price"] = float(avg_price)
        if extra:
            entry["extra"] = extra
        return entry

    @staticmethod
    def _extract_strategy_hint(tags: Optional[List[str]]) -> Optional[str]:
        if not tags:
            return None
        for tag in tags:
            if isinstance(tag, str) and tag.startswith("strategy:"):
                return tag.split(":", 1)[1]
        return None


class OrderPersistenceError(Exception):
    """Raised when persisting an order or execution fails."""


@dataclass
class RouterState:
    mode: str = "dry_run"
    daily_notional_limit: float = 1_000_000.0
    notional_routed: float = 0.0

    ALLOWED_MODES: Tuple[str, ...] = ("sandbox", "live", "dry_run")

    def as_dict(self) -> Dict[str, float | str]:
        return {
            "mode": self.mode,
            "daily_notional_limit": self.daily_notional_limit,
            "notional_routed": self.notional_routed,
        }


def _normalise_router_mode(value: str) -> str:
    cleaned = (value or "").strip().lower()
    if cleaned == "paper":
        cleaned = "sandbox"
    if cleaned not in RouterState.ALLOWED_MODES:
        allowed = "', '".join(RouterState.ALLOWED_MODES)
        raise ValueError(f"mode must be one of '{allowed}'")
    return cleaned


def _public_router_mode(value: str) -> str:
    if value == "paper":
        return "sandbox"
    return value


class OrderRouter:
    """Coordinate brokers, risk and logging."""

    def __init__(
        self,
        adapters: List[BrokerAdapter],
        risk_engine: RiskEngine,
        limit_store: DynamicLimitStore,
        events_publisher: OrderEventsPublisher | None = None,
    ) -> None:
        self._adapters = {adapter.name: adapter for adapter in adapters}
        self._risk_engine = risk_engine
        self._limit_store = limit_store
        self._risk_alerts: List[RiskSignal] = []
        self._lock = threading.RLock()
        self._state = RouterState()
        self._events = events_publisher or NullOrderEventsPublisher()

    def list_brokers(self) -> List[str]:
        return sorted(self._adapters.keys())

    def get_state(self) -> RouterState:
        with self._lock:
            return RouterState(**self._state.__dict__)

    def update_state(self, *, mode: Optional[str] = None, limit: Optional[float] = None) -> RouterState:
        with self._lock:
            if mode is not None:
                normalised = _normalise_router_mode(mode)
                self._state.mode = normalised
            if limit is not None:
                if limit <= 0:
                    raise ValueError("daily_notional_limit must be positive")
                self._state.daily_notional_limit = float(limit)
            return self.get_state()

    def current_mode(self) -> str:
        with self._lock:
            return _public_router_mode(self._state.mode)

    def _apply_daily_limit(self, notional: float) -> None:
        with self._lock:
            projected = self._state.notional_routed + notional
            if projected > self._state.daily_notional_limit:
                raise RuntimeError("Daily notional limit exceeded")
            self._state.notional_routed = projected

    def route_order(
        self,
        order: ExecutionIntent,
        context: Dict[str, Any],
        *,
        session: Session,
    ) -> ExecutionReport:
        broker_name = order.broker
        if broker_name not in self._adapters:
            raise KeyError("Unknown broker")
        adapter = self._adapters[broker_name]
        account_id = str(context.get("account_id") or "default")
        signals = self._risk_engine.evaluate(order, context)
        locks = [signal for signal in signals if signal.level is RiskLevel.LOCK]
        if locks:
            raise ValueError(locks[0].message)
        alerts = [signal for signal in signals if signal.level is RiskLevel.ALERT]
        if alerts:
            self._record_alerts(alerts)

        price_reference = float(order.price or context.get("last_price") or 0.0)
        if price_reference <= 0:
            price_reference = 1.0
        notional = abs(order.quantity) * price_reference
        mode = self.current_mode()
        if mode == "dry_run":
            report = self._build_simulated_report(order, price_reference)
            try:
                self._persist_simulated_execution(
                    session, order, report, account_id
                )
            except OrderPersistenceError:
                raise
            except Exception as exc:  # pragma: no cover - defensive safety net
                logger.exception(
                    "Unexpected error while persisting simulated execution %s",
                    report.order_id,
                )
                raise OrderPersistenceError(
                    "unexpected error while persisting simulated execution"
                ) from exc
            return report

        self._apply_daily_limit(notional)
        response = adapter.place_order(order, reference_price=price_reference)
        try:
            self._persist_order(session, order, response, account_id)
        except OrderPersistenceError:
            raise
        except Exception as exc:  # pragma: no cover - defensive safety net
            logger.exception("Unexpected error while persisting order %s", response.order_id)
            raise OrderPersistenceError("unexpected error while persisting order") from exc
        self._risk_engine.register_execution(order, account_id, price_reference)
        return response

    def cancel(self, broker: str, order_id: str, *, session: Session) -> ExecutionReport:
        if broker not in self._adapters:
            raise KeyError("Unknown broker")
        adapter = self._adapters[broker]
        result = adapter.cancel_order(order_id)
        try:
            self._record_cancellation(session, result)
        except OrderPersistenceError:
            raise
        except Exception as exc:  # pragma: no cover - defensive safety net
            logger.exception(
                "Unexpected error while logging cancellation for order %s", result.order_id
            )
            raise OrderPersistenceError("unexpected error while logging cancellation") from exc
        return result

    def _build_simulated_report(
        self, order: ExecutionIntent, price_reference: float
    ) -> ExecutionReport:
        timestamp = datetime.now(timezone.utc)
        price = float(order.price or price_reference or 0.0)
        if price <= 0:
            price = max(price_reference, 1.0)
        quantity = float(order.quantity)
        fill = ExecutionFill(quantity=quantity, price=price, timestamp=timestamp)
        return ExecutionReport(
            order_id=f"SIM-{uuid4().hex[:12]}",
            status=ExecutionStatus.FILLED,
            broker=order.broker,
            venue=order.venue,
            symbol=order.symbol,
            side=order.side,
            quantity=quantity,
            filled_quantity=quantity,
            avg_price=price,
            submitted_at=timestamp,
            fills=[fill],
            tags=list(order.tags or []),
        )

    def _persist_simulated_execution(
        self,
        session: Session,
        order: ExecutionIntent,
        report: ExecutionReport,
        account_id: str,
    ) -> None:
        notes = self._format_notes(
            "simulated",
            ",".join(order.tags) if order.tags else None,
            f"status={report.status.value}",
        )
        tags = self._merge_tags(order.tags, report.tags)
        try:
            with session.begin():
                simulation = SimulatedExecutionModel(
                    simulation_id=report.order_id,
                    correlation_id=order.client_order_id,
                    account_id=account_id,
                    broker=order.broker,
                    venue=order.venue.value,
                    symbol=order.symbol,
                    side=order.side.value,
                    quantity=self._to_decimal(report.quantity) or Decimal("0"),
                    filled_quantity=self._to_decimal(report.filled_quantity)
                    or Decimal("0"),
                    price=self._to_decimal(report.avg_price) or Decimal("0"),
                    status=report.status.value,
                    submitted_at=report.submitted_at,
                    notes=notes,
                    tags=tags,
                )
                session.add(simulation)
        except SQLAlchemyError as exc:
            logger.exception(
                "Failed to persist simulated execution for %s", report.order_id
            )
            raise OrderPersistenceError(
                "database error while persisting simulated execution"
            ) from exc
        else:
            self._events.simulated_execution(order, report, account_id)

    def _persist_order(
        self,
        session: Session,
        order: ExecutionIntent,
        report: ExecutionReport,
        account_id: str,
    ) -> None:
        notes = self._format_notes(
            ",".join(order.tags) if order.tags else None,
            f"status={report.status.value}",
        )
        tags = self._merge_tags(order.tags, report.tags)
        try:
            with session.begin():
                order_model = OrderModel(
                    external_order_id=report.order_id,
                    correlation_id=order.client_order_id,
                    account_id=account_id,
                    broker=order.broker,
                    venue=order.venue.value,
                    symbol=order.symbol,
                    side=order.side.value,
                    order_type=order.order_type.value,
                    quantity=self._to_decimal(order.quantity),
                    filled_quantity=self._to_decimal(report.filled_quantity),
                    limit_price=self._to_decimal(order.price),
                    status=report.status.value,
                    time_in_force=order.time_in_force.value,
                    submitted_at=report.submitted_at,
                    notes=notes,
                    tags=tags,
                )
                session.add(order_model)
                session.flush()
                for execution in self._build_execution_models(
                    order_model, report, account_id, tags
                ):
                    session.add(execution)
        except SQLAlchemyError as exc:
            logger.exception("Failed to persist order %s", report.order_id)
            raise OrderPersistenceError("database error while persisting order") from exc
        else:
            self._events.order_persisted(order, report, account_id)

    def _record_cancellation(self, session: Session, report: ExecutionReport) -> None:
        order_model: OrderModel | None = None
        try:
            with session.begin():
                order_model = (
                    session.execute(
                        select(OrderModel).where(
                            OrderModel.external_order_id == report.order_id
                        )
                    )
                    .scalars()
                    .first()
                )
                if order_model is None:
                    logger.warning(
                        "Order %s not found while logging cancellation", report.order_id
                    )
                    return
                cancel_identifier = f"{report.order_id}-cancel"
                existing_cancel = (
                    session.execute(
                        select(ExecutionModel).where(
                            ExecutionModel.external_execution_id == cancel_identifier
                        )
                    )
                    .scalars()
                    .first()
                )
                if existing_cancel is not None:
                    logger.debug(
                        "Cancellation for order %s already recorded", report.order_id
                    )
                    return
                order_model.status = report.status.value
                order_model.filled_quantity = self._to_decimal(report.filled_quantity) or Decimal("0")
                cancellation_note = self._format_notes(
                    order_model.notes,
                    f"{report.status.value} at {report.submitted_at.isoformat()}",
                    ",".join(report.tags) if report.tags else None,
                )
                order_model.notes = cancellation_note
                order_model.tags = self._merge_tags(order_model.tags or [], report.tags)
                cancellation_tags = list(order_model.tags or [])
                cancellation_execution = ExecutionModel(
                    order=order_model,
                    external_execution_id=cancel_identifier,
                    correlation_id=order_model.correlation_id,
                    account_id=order_model.account_id,
                    symbol=report.symbol,
                    quantity=Decimal("0"),
                    price=self._to_decimal(report.avg_price) or Decimal("0"),
                    liquidity="cancelled",
                    executed_at=report.submitted_at,
                    notes=cancellation_note,
                    tags=cancellation_tags,
                )
                session.add(cancellation_execution)
        except SQLAlchemyError as exc:
            logger.exception(
                "Failed to log cancellation for order %s", report.order_id
            )
            raise OrderPersistenceError("database error while logging cancellation") from exc
        else:
            if order_model is not None:
                self._events.order_cancelled(order_model, report)

    def _build_execution_models(
        self,
        order_model: OrderModel,
        report: ExecutionReport,
        account_id: str,
        tags: Sequence[str] | None = None,
    ) -> List[ExecutionModel]:
        executions: List[ExecutionModel] = []
        execution_tags = self._merge_tags(tags, report.tags)
        for index, fill in enumerate(report.fills):
            executions.append(
                ExecutionModel(
                    order=order_model,
                    external_execution_id=f"{report.order_id}-fill-{index}",
                    correlation_id=order_model.correlation_id,
                    account_id=account_id,
                    symbol=report.symbol,
                    quantity=self._to_decimal(fill.quantity) or Decimal("0"),
                    price=self._to_decimal(fill.price) or Decimal("0"),
                    executed_at=fill.timestamp,
                    tags=execution_tags,
                )
            )
        return executions

    @staticmethod
    def _format_notes(*parts: Optional[str]) -> Optional[str]:
        combined = " | ".join(part for part in parts if part)
        if not combined:
            return None
        return combined[:255]

    @staticmethod
    def _to_decimal(value: float | int | Decimal | None) -> Optional[Decimal]:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    @staticmethod
    def _merge_tags(*groups: Sequence[str] | None) -> List[str]:
        merged: List[str] = []
        seen: set[str] = set()
        for group in groups:
            if not group:
                continue
            for raw in group:
                if raw is None:
                    continue
                tag = str(raw).strip()
                if not tag:
                    continue
                lower = tag.lower()
                if lower in seen:
                    continue
                merged.append(tag)
                seen.add(lower)
        return merged

    @staticmethod
    def _append_manual_note(existing: Optional[str], new_note: Optional[str]) -> Optional[str]:
        if new_note is None:
            return existing
        trimmed = new_note.strip()
        if not trimmed:
            return existing
        if not existing:
            return trimmed
        if trimmed in existing.splitlines():
            return existing
        return f"{existing}\n{trimmed}"[:2000]

    @staticmethod
    def _build_tag_filter(column, value: str):
        term = (value or "").strip().lower()
        if not term:
            return None
        pattern = f'%"{term}"%'
        return func.lower(cast(column, String)).like(pattern)

    @staticmethod
    def _strategy_search_terms(value: str) -> List[str]:
        if value is None:
            return []
        trimmed = value.strip()
        if not trimmed:
            return []
        lowered = trimmed.lower()
        terms: set[str] = {trimmed, lowered}
        if ":" in trimmed:
            suffix = trimmed.split(":", 1)[1].strip()
            if suffix:
                terms.add(suffix)
                terms.add(suffix.lower())
                terms.add(f"strategy:{suffix}")
                terms.add(f"strategy:{suffix.lower()}")
        else:
            terms.add(f"strategy:{trimmed}")
            terms.add(f"strategy:{lowered}")
        return [term for term in terms if term]

    def orders_log(
        self,
        *,
        session: Session,
        limit: int = 100,
        offset: int = 0,
        account_id: Optional[str] = None,
        symbol: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        tag: Optional[str] = None,
        strategy: Optional[str] = None,
    ) -> Tuple[List[OrderModel], int]:
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        ordering = func.coalesce(OrderModel.submitted_at, OrderModel.created_at)
        statement = (
            select(OrderModel)
            .options(selectinload(OrderModel.executions))
            .order_by(ordering.desc(), OrderModel.created_at.desc())
        )
        count_stmt = select(func.count()).select_from(OrderModel)
        filters = []
        if account_id:
            filters.append(OrderModel.account_id == account_id)
        if symbol:
            filters.append(OrderModel.symbol == symbol)
        if start:
            filters.append(ordering >= start)
        if end:
            filters.append(ordering <= end)
        if tag:
            tag_filter = self._build_tag_filter(OrderModel.tags, tag)
            if tag_filter is not None:
                filters.append(tag_filter)
        if strategy:
            strategy_terms = self._strategy_search_terms(strategy)
            strategy_filters = [
                self._build_tag_filter(OrderModel.tags, term) for term in strategy_terms
            ]
            strategy_filters = [item for item in strategy_filters if item is not None]
            if strategy_filters:
                filters.append(or_(*strategy_filters))
        if filters:
            statement = statement.where(*filters)
            count_stmt = count_stmt.where(*filters)
        statement = statement.offset(offset).limit(limit)
        result = session.execute(statement).unique()
        orders = list(result.scalars().all())
        total = session.execute(count_stmt).scalar_one()
        return orders, total

    def executions(
        self,
        *,
        session: Session,
        limit: int = 100,
        offset: int = 0,
        order_id: Optional[int] = None,
        account_id: Optional[str] = None,
        symbol: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        tag: Optional[str] = None,
        strategy: Optional[str] = None,
    ) -> Tuple[List[ExecutionModel], int]:
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        statement = select(ExecutionModel).order_by(
            ExecutionModel.executed_at.desc(), ExecutionModel.created_at.desc()
        )
        count_stmt = select(func.count()).select_from(ExecutionModel)
        filters = []
        if order_id is not None:
            filters.append(ExecutionModel.order_id == order_id)
        if account_id:
            filters.append(ExecutionModel.account_id == account_id)
        if symbol:
            filters.append(ExecutionModel.symbol == symbol)
        if start:
            filters.append(ExecutionModel.executed_at >= start)
        if end:
            filters.append(ExecutionModel.executed_at <= end)
        if tag:
            tag_filter = self._build_tag_filter(ExecutionModel.tags, tag)
            if tag_filter is not None:
                filters.append(tag_filter)
        if strategy:
            strategy_terms = self._strategy_search_terms(strategy)
            strategy_filters = [
                self._build_tag_filter(ExecutionModel.tags, term)
                for term in strategy_terms
            ]
            strategy_filters = [item for item in strategy_filters if item is not None]
            if strategy_filters:
                filters.append(or_(*strategy_filters))
        if filters:
            statement = statement.where(*filters)
            count_stmt = count_stmt.where(*filters)
        statement = statement.offset(offset).limit(limit)
        executions = list(session.execute(statement).scalars().all())
        total = session.execute(count_stmt).scalar_one()
        return executions, total

    @staticmethod
    def serialize_execution_report(order: OrderModel) -> ExecutionReport:
        fills: List[ExecutionFill] = []
        total_quantity = Decimal("0")
        total_value = Decimal("0")
        for execution in sorted(order.executions, key=lambda item: item.executed_at):
            quantity = execution.quantity or Decimal("0")
            price = execution.price or Decimal("0")
            if quantity <= 0 or price <= 0:
                continue
            total_quantity += quantity
            total_value += quantity * price
            fills.append(
                ExecutionFill(
                    quantity=float(quantity),
                    price=float(price),
                    timestamp=execution.executed_at,
                )
            )

        avg_price: Optional[float] = None
        if total_quantity > 0:
            avg_price = float(total_value / total_quantity)

        submitted_at = order.submitted_at or order.created_at
        if submitted_at is None:
            raise ValueError("Order must have either submitted_at or created_at set")

        return ExecutionReport(
            order_id=order.external_order_id or str(order.id),
            status=ExecutionStatus(order.status),
            broker=order.broker,
            venue=ExecutionVenue(order.venue),
            symbol=order.symbol,
            side=OrderSide(order.side),
            quantity=float(order.quantity),
            filled_quantity=float(order.filled_quantity),
            avg_price=avg_price,
            submitted_at=submitted_at,
            fills=fills,
            tags=list(order.tags or []),
        )

    def _record_alerts(self, alerts: List[RiskSignal]) -> None:
        if not alerts:
            return
        with self._lock:
            self._risk_alerts.extend(alerts)
        for signal in alerts:
            logger.warning(
                "Risk alert triggered - %s: %s",
                signal.rule_id,
                signal.message,
                extra={"metadata": signal.metadata},
            )

    def risk_alerts(self) -> List[RiskSignal]:
        with self._lock:
            return list(self._risk_alerts)

    def set_stop_loss(self, account_id: str, threshold: float) -> None:
        self._limit_store.set_stop_loss(account_id, threshold)


settings = get_settings()

_BINANCE_CLIENT: BinanceClient | None = None
if settings.binance_api_key and settings.binance_api_secret:
    binance_config = BinanceConfig(
        api_key=settings.binance_api_key,
        api_secret=settings.binance_api_secret,
        base_url=settings.binance_api_url,
        recv_window=settings.binance_recv_window,
        timeout=settings.binance_timeout,
        request_rate=settings.binance_requests_per_minute,
        request_interval=settings.binance_rate_interval_seconds,
    )
    _BINANCE_CLIENT = BinanceClient(binance_config)

_IBKR_CLIENT: IBKRClient | None = None
if settings.ibkr_api_key and settings.ibkr_api_secret:
    ibkr_config = IBKRConfig(
        api_key=settings.ibkr_api_key,
        api_secret=settings.ibkr_api_secret,
        base_url=settings.ibkr_api_url,
        account_id=settings.ibkr_account_id,
        timeout=settings.ibkr_timeout,
        request_rate=settings.ibkr_requests_per_minute,
        request_interval=settings.ibkr_rate_interval_seconds,
    )
    _IBKR_CLIENT = IBKRClient(ibkr_config)

_supported_limits = list(iter_supported_pairs())
_symbol_limits = {
    limit.symbol: SymbolLimit(max_position=limit.max_position, max_notional=limit.notional_limit())
    for limit in _supported_limits
}
_notional_limits = {limit.symbol: limit.notional_limit() for limit in _supported_limits}
_limit_store = DynamicLimitStore(_symbol_limits)
_limit_store.set_stop_loss("default", 50_000.0)

_streaming_config = StreamingConfig.from_env()
_streaming_client = StreamingIngestClient(_streaming_config)
_events_publisher = StreamingOrderEventsPublisher(_streaming_client)

router = OrderRouter(
    adapters=[BinanceAdapter(client=_BINANCE_CLIENT), IBKRAdapter(client=_IBKR_CLIENT)],
    risk_engine=RiskEngine(
        [
            DynamicLimitRule(_limit_store),
            StopLossRule(_limit_store, default_threshold=50_000.0),
            MaxDailyLossRule(max_loss=50_000.0),
            MaxNotionalRule(_notional_limits),
        ]
    ),
    limit_store=_limit_store,
    events_publisher=_events_publisher,
)

configure_logging("order-router")

app = FastAPI(title="Order Router", version="0.1.0")
install_entitlements_middleware(app, required_capabilities=["can.route_orders"])
app.add_middleware(RequestContextMiddleware, service_name="order-router")
setup_metrics(app, service_name="order-router")


@app.on_event("startup")
async def _configure_streaming_client() -> None:
    global _streaming_client, _events_publisher, _streaming_config
    if _streaming_client.enabled:
        await _streaming_client.aclose()
    _streaming_config = StreamingConfig.from_env()
    _streaming_client = StreamingIngestClient(_streaming_config)
    _events_publisher = StreamingOrderEventsPublisher(_streaming_client)
    router._events = _events_publisher  # type: ignore[attr-defined]
    if _streaming_client.enabled:
        _streaming_client.bind_loop(asyncio.get_running_loop())
        streaming_logger.info(
            "Streaming ingest enabled for room %s", _streaming_config.room_id
        )
        try:
            with closing(SessionLocal()) as session:
                _events_publisher.reload_state(session)
        except Exception as exc:  # pragma: no cover - defensive logging
            streaming_logger.warning(
                "Unable to preload portfolio snapshot", exc_info=exc
            )
    else:
        streaming_logger.info(
            "Streaming ingest disabled (missing STREAMING_INGEST_URL or STREAMING_SERVICE_TOKEN)"
        )


@app.on_event("shutdown")
async def _shutdown_streaming_client() -> None:
    await _streaming_client.aclose()
    if _BINANCE_CLIENT is not None:
        _BINANCE_CLIENT.close()
    if _IBKR_CLIENT is not None:
        _IBKR_CLIENT.close()


class ExecutionPlanResponse(BaseModel):
    plan: ExecutionPlan


class CancelPayload(BaseModel):
    order_id: str


class RiskAlertResponse(BaseModel):
    rule_id: str
    level: RiskLevel
    message: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StateUpdatePayload(BaseModel):
    mode: Optional[str] = Field(default=None, pattern="^(sandbox|paper|live|dry_run)$")
    daily_notional_limit: Optional[float] = Field(default=None, gt=0)


class ExecutionModeResponse(BaseModel):
    mode: str = Field(pattern="^(sandbox|dry_run|live)$")
    allowed_modes: Tuple[str, str] = ("sandbox", "dry_run")


class ExecutionModeUpdate(BaseModel):
    mode: str = Field(pattern="^(sandbox|dry_run)$")


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/brokers")
def list_brokers() -> Dict[str, List[str]]:
    return {"brokers": router.list_brokers()}


@app.post("/plans", response_model=ExecutionPlanResponse)
def preview_execution_plan(payload: ExecutionIntent) -> ExecutionPlanResponse:
    limit = get_pair_limit(payload.venue, payload.symbol)
    if limit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unsupported trading pair")
    if payload.quantity > limit.max_order_size:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order size exceeds sandbox limit")
    return ExecutionPlanResponse(plan=build_plan(payload))


@app.post("/orders", response_model=ExecutionReport, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: ExecutionIntent,
    request: Request,
    session: Session = Depends(get_session),
) -> ExecutionReport:
    entitlements = getattr(request.state, "entitlements", None)
    bypass = getattr(entitlements, "customer_id", None) == "anonymous"
    if entitlements and not bypass and not entitlements.has("can.route_orders"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing capability")
    limit = get_pair_limit(payload.venue, payload.symbol)
    if limit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unsupported trading pair")
    if payload.quantity > limit.max_order_size:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order size exceeds sandbox limit")
    risk_payload = payload.risk.model_dump(exclude_unset=True) if payload.risk else {}
    account_id = payload.account_id or risk_payload.get("account_id") or "default"
    risk_payload["account_id"] = account_id
    risk_overrides = RiskOverrides(**risk_payload)
    if risk_overrides.stop_loss:
        router.set_stop_loss(risk_overrides.account_id, risk_overrides.stop_loss)
    context: Dict[str, Any] = {
        "daily_loss": 0.0,
        "last_price": payload.price or limit.reference_price,
        "account_id": risk_overrides.account_id,
        "realized_pnl": risk_overrides.realized_pnl or 0.0,
        "unrealized_pnl": risk_overrides.unrealized_pnl or 0.0,
        "stop_loss": risk_overrides.stop_loss,
    }
    try:
        result = router.route_order(payload, context, session=session)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OrderPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist order",
        ) from exc
    return result


@app.post("/orders/{broker}/cancel", response_model=ExecutionReport)
def cancel_order(
    broker: str,
    payload: CancelPayload,
    session: Session = Depends(get_session),
) -> ExecutionReport:
    try:
        return router.cancel(broker, payload.order_id, session=session)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OrderPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist cancellation",
        ) from exc


@app.get("/orders/log", response_model=PaginatedOrders)
def get_orders_log(
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="Maximum number of orders to return (pagination).",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of orders to skip from the beginning (pagination).",
    ),
    symbol: Optional[str] = Query(
        default=None,
        description="Return only orders for the given trading symbol.",
    ),
    account_id: Optional[str] = Query(
        default=None,
        min_length=1,
        max_length=64,
        description="Return only orders associated with this account identifier.",
    ),
    start: Optional[datetime] = Query(
        default=None,
        description="Return orders submitted or created at or after this ISO 8601 timestamp.",
    ),
    end: Optional[datetime] = Query(
        default=None,
        description="Return orders submitted or created before or at this ISO 8601 timestamp.",
    ),
    tag: Optional[str] = Query(
        default=None,
        description="Return only orders tagged with the provided label.",
    ),
    strategy: Optional[str] = Query(
        default=None,
        description="Return only orders annotated for the provided strategy identifier.",
    ),
    session: Session = Depends(get_session),
) -> PaginatedOrders:
    orders, total = router.orders_log(
        session=session,
        limit=limit,
        offset=offset,
        account_id=account_id,
        symbol=symbol,
        start=start,
        end=end,
        tag=tag,
        strategy=strategy,
    )
    return PaginatedOrders(
        items=[OrderRecord.model_validate(order, from_attributes=True) for order in orders],
        metadata=OrdersLogMetadata(
            limit=limit,
            offset=offset,
            total=total,
            account_id=account_id,
            symbol=symbol,
            start=start,
            end=end,
            tag=tag,
            strategy=strategy,
        ),
    )


@app.post("/orders/{order_id}/notes", response_model=OrderRecord)
def annotate_order(
    order_id: int,
    payload: OrderAnnotationPayload,
    session: Session = Depends(get_session),
) -> OrderRecord:
    order = (
        session.execute(
            select(OrderModel)
            .options(selectinload(OrderModel.executions))
            .where(OrderModel.id == order_id)
        )
        .scalars()
        .first()
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    new_note = payload.notes.strip() if payload.notes else None
    new_tags = OrderRouter._merge_tags(order.tags or [], payload.tags)

    try:
        if new_note:
            order.notes = OrderRouter._append_manual_note(order.notes, new_note)
        if new_tags:
            order.tags = new_tags
        for execution in order.executions:
            if new_note:
                execution.notes = OrderRouter._append_manual_note(execution.notes, new_note)
            if new_tags:
                execution.tags = OrderRouter._merge_tags(execution.tags or [], new_tags)
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        logger.exception("Failed to annotate order %s", order_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to persist order annotation.",
        ) from exc

    session.refresh(order)
    return OrderRecord.model_validate(order, from_attributes=True)


@app.get("/executions", response_model=PaginatedExecutions)
def get_executions(
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="Maximum number of executions to return (pagination).",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of executions to skip from the beginning (pagination).",
    ),
    order_id: Optional[int] = Query(
        default=None,
        ge=1,
        description="Return only executions associated with this internal order identifier.",
    ),
    symbol: Optional[str] = Query(
        default=None,
        description="Return only executions for the given trading symbol.",
    ),
    account_id: Optional[str] = Query(
        default=None,
        min_length=1,
        max_length=64,
        description="Return only executions associated with this account identifier.",
    ),
    start: Optional[datetime] = Query(
        default=None,
        description="Return executions that occurred at or after this ISO 8601 timestamp.",
    ),
    end: Optional[datetime] = Query(
        default=None,
        description="Return executions that occurred before or at this ISO 8601 timestamp.",
    ),
    tag: Optional[str] = Query(
        default=None,
        description="Return only executions tagged with the provided label.",
    ),
    strategy: Optional[str] = Query(
        default=None,
        description="Return only executions linked to the provided strategy identifier.",
    ),
    session: Session = Depends(get_session),
) -> PaginatedExecutions:
    executions, total = router.executions(
        session=session,
        limit=limit,
        offset=offset,
        order_id=order_id,
        account_id=account_id,
        symbol=symbol,
        start=start,
        end=end,
        tag=tag,
        strategy=strategy,
    )
    return PaginatedExecutions(
        items=[
            ExecutionRecord.model_validate(execution, from_attributes=True)
            for execution in executions
        ],
        metadata=ExecutionsMetadata(
            limit=limit,
            offset=offset,
            total=total,
            order_id=order_id,
            account_id=account_id,
            symbol=symbol,
            start=start,
            end=end,
        ),
    )


@app.get("/positions", response_model=PositionsResponse)
def list_positions(session: Session = Depends(get_session)) -> PositionsResponse:
    """Return an aggregated view of current positions."""

    return build_positions_response(session)


@app.post("/positions/{position_id}/close", response_model=PositionCloseResponse)
def close_position(
    position_id: str,
    payload: PositionCloseRequest | None = None,
    session: Session = Depends(get_session),
) -> PositionCloseResponse:
    """Route a market order to close or resize the requested position."""

    try:
        decoded_account, decoded_symbol = decode_position_key(position_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Identifiant de position invalide.",
        ) from exc

    snapshot = rebuild_positions_snapshot(session)
    holding: Dict[str, Any] | None = None
    owner: str | None = None
    for portfolio in snapshot:
        for candidate in portfolio.get("holdings", []):
            if candidate.get("id") == position_id:
                holding = candidate
                owner = portfolio.get("owner")
                break
        if holding:
            break
    if holding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position introuvable.")

    symbol = str(holding.get("symbol") or decoded_symbol).strip()
    if not symbol:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Symbole manquant pour la position.")
    account_id = str(holding.get("account_id") or owner or decoded_account).strip() or "default"
    current_quantity = float(holding.get("quantity") or 0.0)
    target_quantity = (
        float(payload.target_quantity)
        if payload and payload.target_quantity is not None
        else 0.0
    )
    delta = target_quantity - current_quantity
    if math.isclose(delta, 0.0, abs_tol=PortfolioAggregator._EPSILON):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La position est déjà alignée sur la cible demandée.",
        )

    side = OrderSide.BUY if delta > 0 else OrderSide.SELL
    quantity = abs(delta)

    order_statement = (
        select(OrderModel)
        .where(
            OrderModel.account_id == account_id,
            OrderModel.symbol == symbol,
        )
        .order_by(OrderModel.created_at.desc())
        .limit(1)
    )
    order_model = session.execute(order_statement).scalars().first()
    if order_model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Impossible de déterminer le broker associé à la position.",
        )

    try:
        venue = ExecutionVenue(order_model.venue)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La position est associée à une place de marché inconnue.",
        ) from exc

    limit = get_pair_limit(venue, symbol)
    if limit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cette paire n'est pas disponible dans l'environnement de simulation.",
        )
    if quantity > limit.max_order_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La taille demandée dépasse la limite autorisée pour cette paire.",
        )

    tags = [f"position:{position_id}"]
    if math.isclose(target_quantity, 0.0, abs_tol=PortfolioAggregator._EPSILON):
        tags.append("position:close")
    else:
        tags.append("position:adjust")

    intent = ExecutionIntent(
        broker=order_model.broker,
        venue=venue,
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.IOC,
        account_id=account_id,
        tags=tags,
        risk=RiskOverrides(account_id=account_id),
    )

    last_price = float(holding.get("current_price") or limit.reference_price)
    context: Dict[str, Any] = {
        "daily_loss": 0.0,
        "last_price": last_price,
        "account_id": account_id,
        "realized_pnl": 0.0,
        "unrealized_pnl": float(holding.get("market_value") or 0.0),
        "stop_loss": None,
    }

    # Reset the transactional state before delegating order persistence. SQLAlchemy
    # implicitly begins a transaction as soon as the session is used for reads,
    # which would cause ``session.begin()`` inside ``router.route_order`` to
    # raise. Rolling back clears the transactional context while keeping the
    # session usable for subsequent queries.
    session.rollback()

    try:
        report = router.route_order(intent, context, session=session)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OrderPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de l'enregistrement de l'ordre de clôture.",
        ) from exc

    session.expire_all()
    positions = build_positions_response(session)
    return PositionCloseResponse(order=report, positions=positions)


@app.get("/risk/alerts", response_model=List[RiskAlertResponse])
def get_risk_alerts() -> List[RiskAlertResponse]:
    return [
        RiskAlertResponse(
            rule_id=alert.rule_id,
            level=alert.level,
            message=alert.message,
            metadata=alert.metadata,
        )
        for alert in router.risk_alerts()
    ]


@app.get("/mode", response_model=ExecutionModeResponse)
def get_execution_mode() -> ExecutionModeResponse:
    """Return the current execution mode for the router."""

    return ExecutionModeResponse(mode=router.current_mode())


@app.post("/mode", response_model=ExecutionModeResponse)
def set_execution_mode(payload: ExecutionModeUpdate) -> ExecutionModeResponse:
    """Update the execution mode, restricting choices to sandbox or dry-run."""

    try:
        router.update_state(mode=payload.mode)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ExecutionModeResponse(mode=router.current_mode())


@app.get("/state")
def get_state() -> Dict[str, float | str]:
    return router.get_state().as_dict()


@app.put("/state")
def update_state(payload: StateUpdatePayload) -> Dict[str, float | str]:
    data = payload.model_dump(exclude_unset=True)
    try:
        state = router.update_state(
            mode=data.get("mode"),
            limit=data.get("daily_notional_limit"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return state.as_dict()


__all__ = ["app", "router"]
