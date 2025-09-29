"""Order router service centralising broker connectivity."""
from __future__ import annotations

from datetime import datetime
import logging
import threading
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from libs.entitlements import install_entitlements_middleware
from libs.observability.logging import RequestContextMiddleware, configure_logging
from libs.observability.metrics import setup_metrics
from infra.trading_models import Execution as ExecutionModel
from infra.trading_models import Order as OrderModel
from providers.limits import build_plan, get_pair_limit, iter_supported_pairs
from schemas.market import (
    ExecutionFill,
    ExecutionPlan,
    ExecutionStatus,
    ExecutionVenue,
    OrderSide,
)
from schemas.order_router import (
    ExecutionIntent,
    ExecutionRecord,
    ExecutionReport,
    ExecutionsMetadata,
    OrderRecord,
    OrdersLogMetadata,
    PaginatedExecutions,
    PaginatedOrders,
    RiskOverrides,
)

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


class OrderPersistenceError(Exception):
    """Raised when persisting an order or execution fails."""


@dataclass
class RouterState:
    mode: str = "paper"
    daily_notional_limit: float = 1_000_000.0
    notional_routed: float = 0.0

    def as_dict(self) -> Dict[str, float | str]:
        return {
            "mode": self.mode,
            "daily_notional_limit": self.daily_notional_limit,
            "notional_routed": self.notional_routed,
        }


class OrderRouter:
    """Coordinate brokers, risk and logging."""

    def __init__(
        self,
        adapters: List[BrokerAdapter],
        risk_engine: RiskEngine,
        limit_store: DynamicLimitStore,
    ) -> None:
        self._adapters = {adapter.name: adapter for adapter in adapters}
        self._risk_engine = risk_engine
        self._limit_store = limit_store
        self._risk_alerts: List[RiskSignal] = []
        self._lock = threading.RLock()
        self._state = RouterState()

    def list_brokers(self) -> List[str]:
        return sorted(self._adapters.keys())

    def get_state(self) -> RouterState:
        with self._lock:
            return RouterState(**self._state.__dict__)

    def update_state(self, *, mode: Optional[str] = None, limit: Optional[float] = None) -> RouterState:
        with self._lock:
            if mode is not None:
                if mode not in {"paper", "live"}:
                    raise ValueError("mode must be 'paper' or 'live'")
                self._state.mode = mode
            if limit is not None:
                if limit <= 0:
                    raise ValueError("daily_notional_limit must be positive")
                self._state.daily_notional_limit = float(limit)
            return self.get_state()

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
                )
                session.add(order_model)
                session.flush()
                for execution in self._build_execution_models(
                    order_model, report, account_id
                ):
                    session.add(execution)
        except SQLAlchemyError as exc:
            logger.exception("Failed to persist order %s", report.order_id)
            raise OrderPersistenceError("database error while persisting order") from exc

    def _record_cancellation(self, session: Session, report: ExecutionReport) -> None:
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
                )
                session.add(cancellation_execution)
        except SQLAlchemyError as exc:
            logger.exception(
                "Failed to log cancellation for order %s", report.order_id
            )
            raise OrderPersistenceError("database error while logging cancellation") from exc

    def _build_execution_models(
        self,
        order_model: OrderModel,
        report: ExecutionReport,
        account_id: str,
    ) -> List[ExecutionModel]:
        executions: List[ExecutionModel] = []
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
            tags=[],
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


_supported_limits = list(iter_supported_pairs())
_symbol_limits = {
    limit.symbol: SymbolLimit(max_position=limit.max_position, max_notional=limit.notional_limit())
    for limit in _supported_limits
}
_notional_limits = {limit.symbol: limit.notional_limit() for limit in _supported_limits}
_limit_store = DynamicLimitStore(_symbol_limits)
_limit_store.set_stop_loss("default", 50_000.0)

router = OrderRouter(
    adapters=[BinanceAdapter(), IBKRAdapter()],
    risk_engine=RiskEngine(
        [
            DynamicLimitRule(_limit_store),
            StopLossRule(_limit_store, default_threshold=50_000.0),
            MaxDailyLossRule(max_loss=50_000.0),
            MaxNotionalRule(_notional_limits),
        ]
    ),
    limit_store=_limit_store,
)

configure_logging("order-router")

app = FastAPI(title="Order Router", version="0.1.0")
install_entitlements_middleware(app, required_capabilities=["can.route_orders"])
app.add_middleware(RequestContextMiddleware, service_name="order-router")
setup_metrics(app, service_name="order-router")


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
    mode: Optional[str] = Field(default=None, pattern="^(paper|live)$")
    daily_notional_limit: Optional[float] = Field(default=None, gt=0)


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
        ),
    )


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
