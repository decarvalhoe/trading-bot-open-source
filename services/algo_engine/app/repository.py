"""Persistence layer for strategies backed by PostgreSQL."""

from __future__ import annotations

import copy
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, MutableMapping, Tuple

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from infra.strategy_models import (
    Strategy,
    StrategyBacktest,
    StrategyBase,
    StrategyExecution,
    StrategyVersion,
)


class StrategyStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    ERROR = "ERROR"


@dataclass
class StrategyRecord:
    id: str
    name: str
    strategy_type: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = False
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_format: str | None = None
    source: str | None = None
    derived_from: str | None = None
    last_backtest: Dict[str, Any] | None = None
    status: StrategyStatus = StrategyStatus.PENDING
    last_error: str | None = None
    version: int = 1

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


class StrategyRepository:
    """Thread-safe repository caching strategy metadata in memory."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        max_execution_history: int = 50,
    ) -> None:
        self._session_factory = session_factory
        self._lock = threading.RLock()
        self._strategies: MutableMapping[str, StrategyRecord] = {}
        self._max_execution_history = max_execution_history
        self._allowed_transitions: Dict[StrategyStatus, List[StrategyStatus]] = {
            StrategyStatus.PENDING: [StrategyStatus.ACTIVE, StrategyStatus.ERROR],
            StrategyStatus.ACTIVE: [StrategyStatus.ERROR],
            StrategyStatus.ERROR: [StrategyStatus.ACTIVE],
        }
        self._ensure_schema()
        self._refresh_cache()

    def _ensure_schema(self) -> None:
        with self._session_factory() as session:
            bind = session.get_bind()
            if bind is not None:
                StrategyBase.metadata.create_all(bind=bind)  # pragma: no cover - schema bootstrap

    def _refresh_cache(self) -> None:
        with self._session_factory() as session:
            records = session.execute(select(Strategy)).scalars().all()
        cache: MutableMapping[str, StrategyRecord] = {}
        for model in records:
            record = self._to_record(model)
            cache[record.id] = record
        with self._lock:
            self._strategies = cache

    def refresh(self) -> None:
        """Reload the in-memory cache from the database."""

        self._refresh_cache()

    def _ensure_metadata(self, metadata: Dict[str, Any] | None, strategy_id: str) -> Dict[str, Any]:
        data = dict(metadata or {})
        data.setdefault("strategy_id", strategy_id)
        return data

    def _to_record(self, model: Strategy) -> StrategyRecord:
        metadata = self._ensure_metadata(model.metadata_, model.id)
        parameters = dict(model.parameters or {})
        tags = list(model.tags or [])
        last_backtest = model.last_backtest if isinstance(model.last_backtest, dict) else None
        status = StrategyStatus(model.status)
        return StrategyRecord(
            id=model.id,
            name=model.name,
            strategy_type=model.strategy_type,
            parameters=parameters,
            enabled=bool(model.enabled),
            tags=tags,
            metadata=metadata,
            source_format=model.source_format,
            source=model.source,
            derived_from=model.derived_from,
            last_backtest=last_backtest,
            status=status,
            last_error=model.last_error,
            version=model.version or 1,
        )

    def _copy(self, record: StrategyRecord) -> StrategyRecord:
        return copy.deepcopy(record)

    def list(self) -> List[StrategyRecord]:
        with self._lock:
            return [self._copy(record) for record in self._strategies.values()]

    def get(self, strategy_id: str) -> StrategyRecord:
        with self._lock:
            record = self._strategies.get(strategy_id)
        if record is not None:
            return self._copy(record)
        loaded = self._load_strategy(strategy_id)
        if loaded is None:
            raise KeyError("strategy not found")
        return self._copy(loaded)

    def _load_strategy(self, strategy_id: str) -> StrategyRecord | None:
        with self._session_factory() as session:
            model = session.get(Strategy, strategy_id)
        if model is None:
            return None
        record = self._to_record(model)
        with self._lock:
            self._strategies[strategy_id] = record
        return record

    def create(self, record: StrategyRecord) -> StrategyRecord:
        metadata = self._ensure_metadata(record.metadata, record.id)
        with self._session_factory() as session:
            model = Strategy(
                id=record.id,
                name=record.name,
                strategy_type=record.strategy_type,
                version=record.version,
                parameters=dict(record.parameters or {}),
                enabled=bool(record.enabled),
                tags=list(record.tags or []),
                metadata_=metadata,
                source_format=record.source_format,
                source=record.source,
                derived_from=record.derived_from,
                status=record.status.value,
                last_error=record.last_error,
                last_backtest=record.last_backtest,
            )
            session.add(model)
            session.flush()
            session.add(
                StrategyVersion(
                    strategy_id=model.id,
                    version=model.version or 1,
                    name=model.name,
                    strategy_type=model.strategy_type,
                    parameters=model.parameters,
                    metadata_=model.metadata_,
                    tags=model.tags,
                    source_format=model.source_format,
                    source=model.source,
                    derived_from=model.derived_from,
                )
            )
            session.commit()
            session.refresh(model)
        stored = self._to_record(model)
        with self._lock:
            self._strategies[stored.id] = stored
        return self._copy(stored)

    def update(self, strategy_id: str, **updates: Any) -> StrategyRecord:
        with self._lock:
            current = self._strategies.get(strategy_id)
        if current is None:
            current = self._load_strategy(strategy_id)
            if current is None:
                raise KeyError("strategy not found")

        status_update = updates.pop("status", None)
        error_update = updates.pop("last_error", None)

        if status_update is not None and not isinstance(status_update, StrategyStatus):
            status_update = StrategyStatus(status_update)

        if status_update is not None and status_update != current.status:
            allowed = self._allowed_transitions.get(current.status, [])
            if status_update not in allowed:
                raise ValueError(
                    f"Invalid status transition from {current.status.value} to {status_update.value}"
                )
        else:
            status_update = status_update or current.status

        create_version = self._should_snapshot(updates)

        with self._session_factory() as session:
            model = session.get(Strategy, strategy_id)
            if model is None:
                raise KeyError("strategy not found")

            if "name" in updates and updates["name"] is not None:
                model.name = updates["name"]
            if "parameters" in updates:
                model.parameters = dict(updates["parameters"] or {})
            if "tags" in updates:
                model.tags = list(updates["tags"] or [])
            if "metadata" in updates:
                model.metadata_ = dict(updates["metadata"] or {})
            if "source_format" in updates:
                model.source_format = updates["source_format"]
            if "source" in updates:
                model.source = updates["source"]
            if "derived_from" in updates:
                model.derived_from = updates["derived_from"]
            if "enabled" in updates and updates["enabled"] is not None:
                model.enabled = bool(updates["enabled"])
            if "last_backtest" in updates:
                model.last_backtest = updates["last_backtest"]

            model.metadata_ = self._ensure_metadata(model.metadata_, strategy_id)

            if status_update is not None:
                model.status = status_update.value
                if status_update == StrategyStatus.ERROR:
                    if error_update is not None:
                        model.last_error = error_update
                elif status_update == StrategyStatus.ACTIVE:
                    model.last_error = None
                elif error_update is not None:
                    model.last_error = error_update
            elif error_update is not None:
                model.last_error = error_update

            if create_version:
                model.version = (model.version or 1) + 1
                session.add(
                    StrategyVersion(
                        strategy_id=model.id,
                        version=model.version,
                        name=model.name,
                        strategy_type=model.strategy_type,
                        parameters=model.parameters,
                        metadata_=model.metadata_,
                        tags=model.tags,
                        source_format=model.source_format,
                        source=model.source,
                        derived_from=model.derived_from,
                    )
                )

            session.add(model)
            session.commit()
            session.refresh(model)

        stored = self._to_record(model)
        with self._lock:
            self._strategies[stored.id] = stored
        return self._copy(stored)

    def _should_snapshot(self, updates: Dict[str, Any]) -> bool:
        tracked: Iterable[str] = (
            "name",
            "parameters",
            "metadata",
            "tags",
            "source_format",
            "source",
            "enabled",
            "derived_from",
        )
        return any(key in updates for key in tracked)

    def delete(self, strategy_id: str) -> None:
        with self._session_factory() as session:
            model = session.get(Strategy, strategy_id)
            if model is None:
                raise KeyError("strategy not found")
            session.delete(model)
            session.commit()
        with self._lock:
            self._strategies.pop(strategy_id, None)

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for record in self._strategies.values() if record.enabled)

    def clear(self) -> None:
        """Remove all strategies and executions. Intended for tests."""

        with self._session_factory() as session:
            session.execute(delete(StrategyBacktest))
            session.execute(delete(StrategyExecution))
            session.execute(delete(StrategyVersion))
            session.execute(delete(Strategy))
            session.commit()
        with self._lock:
            self._strategies.clear()

    def record_execution(self, strategy_id: str, payload: Dict[str, Any]) -> None:
        submitted_at = self._parse_timestamp(payload.get("submitted_at"))
        with self._session_factory() as session:
            session.add(
                StrategyExecution(
                    strategy_id=strategy_id,
                    order_id=str(payload.get("order_id")),
                    status=str(payload.get("status")),
                    broker=str(payload.get("broker")),
                    venue=str(payload.get("venue")),
                    symbol=str(payload.get("symbol")),
                    side=str(payload.get("side")),
                    quantity=float(payload.get("quantity", 0.0) or 0.0),
                    filled_quantity=float(payload.get("filled_quantity", 0.0) or 0.0),
                    avg_price=(
                        float(payload.get("avg_price"))
                        if payload.get("avg_price") is not None
                        else None
                    ),
                    submitted_at=submitted_at,
                    payload=payload,
                )
            )
            session.commit()

    def get_recent_executions(
        self, *, limit: int | None = None, strategy_id: str | None = None
    ) -> List[Dict[str, Any]]:
        limit = limit or self._max_execution_history
        stmt = select(StrategyExecution).order_by(StrategyExecution.submitted_at.desc())
        if strategy_id is not None:
            stmt = stmt.where(StrategyExecution.strategy_id == strategy_id)
        stmt = stmt.limit(limit)
        with self._session_factory() as session:
            executions = session.execute(stmt).scalars().all()
        return [dict(exec.payload) for exec in executions if isinstance(exec.payload, dict)]

    def record_backtest(
        self,
        strategy_id: str,
        summary: Dict[str, Any],
        *,
        ran_at: datetime | None = None,
    ) -> None:
        """Persist a backtest summary for historical reporting."""

        timestamp = ran_at or datetime.now(timezone.utc)
        equity_curve = summary.get("equity_curve")
        if not isinstance(equity_curve, list):
            equity_curve = []
        payload = dict(summary)
        payload.setdefault("metadata", {})
        payload["ran_at"] = timestamp.isoformat()

        with self._session_factory() as session:
            session.add(
                StrategyBacktest(
                    strategy_id=strategy_id,
                    ran_at=timestamp,
                    initial_balance=float(summary.get("initial_balance", 0.0) or 0.0),
                    profit_loss=float(summary.get("profit_loss", 0.0) or 0.0),
                    total_return=float(summary.get("total_return", 0.0) or 0.0),
                    max_drawdown=float(summary.get("max_drawdown", 0.0) or 0.0),
                    equity_curve=list(equity_curve),
                    summary=payload,
                )
            )
            session.commit()

    def get_backtests(
        self,
        strategy_id: str,
        *,
        limit: int = 25,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Return paginated backtest history for a strategy."""

        stmt = (
            select(StrategyBacktest)
            .where(StrategyBacktest.strategy_id == strategy_id)
            .order_by(StrategyBacktest.ran_at.desc())
            .limit(limit)
            .offset(offset)
        )
        count_stmt = (
            select(func.count())
            .select_from(StrategyBacktest)
            .where(StrategyBacktest.strategy_id == strategy_id)
        )
        with self._session_factory() as session:
            results = session.execute(stmt).scalars().all()
            total = session.execute(count_stmt).scalar_one()

        items: List[Dict[str, Any]] = []
        for record in results:
            summary = dict(record.summary or {})
            summary.setdefault("ran_at", record.ran_at.isoformat())
            summary.setdefault("initial_balance", record.initial_balance)
            summary.setdefault("profit_loss", record.profit_loss)
            summary.setdefault("total_return", record.total_return)
            summary.setdefault("max_drawdown", record.max_drawdown)
            summary.setdefault("equity_curve", record.equity_curve or [])
            items.append(summary)
        return items, int(total)

    def _parse_timestamp(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                parsed = datetime.now(tz=timezone.utc)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        return datetime.now(tz=timezone.utc)


__all__ = ["StrategyRecord", "StrategyRepository", "StrategyStatus"]
