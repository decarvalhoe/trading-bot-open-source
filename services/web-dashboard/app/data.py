"""Sample data served by the web dashboard service."""

from __future__ import annotations

import logging
import math
import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from statistics import mean, stdev
from typing import Dict, Iterable, List, Sequence
from urllib.parse import urljoin

import httpx

from .schemas import (
    Alert,
    DashboardContext,
    Holding,
    LiveLogEntry,
    PerformanceMetrics,
    Portfolio,
    PortfolioHistorySeries,
    PortfolioTimeseriesPoint,
    RiskLevel,
    StrategyExecutionSnapshot,
    StrategyRuntimeStatus,
    StrategyStatus,
    Transaction,
)


logger = logging.getLogger(__name__)

REPORTS_BASE_URL = os.getenv("WEB_DASHBOARD_REPORTS_BASE_URL", "http://reports:8000/")
REPORTS_TIMEOUT_SECONDS = float(os.getenv("WEB_DASHBOARD_REPORTS_TIMEOUT", "5.0"))
ORCHESTRATOR_BASE_URL = os.getenv(
    "WEB_DASHBOARD_ORCHESTRATOR_BASE_URL",
    "http://algo-engine:8000/",
)
ORCHESTRATOR_TIMEOUT_SECONDS = float(os.getenv("WEB_DASHBOARD_ORCHESTRATOR_TIMEOUT", "5.0"))
MAX_LOG_ENTRIES = int(os.getenv("WEB_DASHBOARD_MAX_LOG_ENTRIES", "100"))


def _build_portfolios() -> List[Portfolio]:
    return [
        Portfolio(
            name="Growth",
            owner="alice",
            holdings=[
                Holding(symbol="AAPL", quantity=12, average_price=154.2, current_price=178.4),
                Holding(symbol="MSFT", quantity=5, average_price=298.1, current_price=310.6),
            ],
        ),
        Portfolio(
            name="Income",
            owner="bob",
            holdings=[
                Holding(symbol="TLT", quantity=20, average_price=100.5, current_price=98.2),
                Holding(symbol="XOM", quantity=15, average_price=88.5, current_price=105.7),
            ],
        ),
    ]


def _build_transactions() -> List[Transaction]:
    base_time = datetime.utcnow()
    return [
        Transaction(
            timestamp=base_time - timedelta(hours=2),
            symbol="AAPL",
            side="buy",
            quantity=5,
            price=177.9,
            portfolio="Growth",
        ),
        Transaction(
            timestamp=base_time - timedelta(hours=5),
            symbol="XOM",
            side="sell",
            quantity=3,
            price=104.1,
            portfolio="Income",
        ),
        Transaction(
            timestamp=base_time - timedelta(days=1, hours=1),
            symbol="BTC-USD",
            side="buy",
            quantity=0.25,
            price=Decimal("43750.00"),
            portfolio="Growth",
        ),
    ]


def _build_alerts() -> List[Alert]:
    base_time = datetime.utcnow()
    return [
        Alert(
            id="maint-margin",
            title="Maintenance margin nearing threshold",
            detail="Portfolio Growth is at 82% of the allowed maintenance margin.",
            risk=RiskLevel.warning,
            created_at=base_time - timedelta(minutes=35),
        ),
        Alert(
            id="drawdown",
            title="Daily drawdown limit exceeded",
            detail="Income portfolio dropped 6% over the last trading session.",
            risk=RiskLevel.critical,
            created_at=base_time - timedelta(hours=7),
        ),
        Alert(
            id="news",
            title="Breaking news on AAPL",
            detail="Apple announces quarterly earnings call for next Tuesday.",
            risk=RiskLevel.info,
            created_at=base_time - timedelta(hours=1, minutes=10),
            acknowledged=True,
        ),
    ]


def _coerce_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_session_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # Accept both date and datetime inputs.
        parsed = datetime.fromisoformat(value)
        if isinstance(parsed, datetime):
            return parsed
    except ValueError:
        try:
            return datetime.combine(date.fromisoformat(value), datetime.min.time())
        except ValueError:
            return None
    return None


def _normalise_base_url(base_url: str) -> str:
    if not base_url.endswith("/"):
        return f"{base_url}/"
    return base_url


def _parse_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        parsed = _parse_session_date(value)
        if parsed:
            return parsed
    return None


def _coerce_optional_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_exposure(entry: dict[str, object]) -> float:
    for key in ("exposure", "notional_exposure", "gross_exposure", "net_exposure"):
        if key in entry:
            exposure = _coerce_float(entry.get(key))
            if exposure:
                return exposure
    return 0.0


def _compute_returns(entries: Iterable[dict[str, object]], pnls: List[float]) -> tuple[List[float], bool]:
    exposures = [_extract_exposure(entry) for entry in entries]
    has_exposure = any(abs(exposure) > 0 for exposure in exposures)
    if not has_exposure:
        return pnls.copy(), False

    returns: List[float] = []
    for pnl, exposure in zip(pnls, exposures):
        if not exposure:
            continue
        returns.append(pnl / exposure)
    if not returns:
        return pnls.copy(), False
    return returns, True


def _compute_cumulative_return(returns: List[float], exposure_normalised: bool) -> tuple[float, bool]:
    if not returns:
        return 0.0, False
    if not exposure_normalised:
        return sum(returns), False
    cumulative = 1.0
    for daily_return in returns:
        cumulative *= 1 + daily_return
    return cumulative - 1, True


def _compute_sharpe(returns: List[float]) -> float | None:
    if len(returns) < 2:
        return None
    volatility = stdev(returns)
    if not volatility:
        return None
    return (mean(returns) / volatility) * math.sqrt(252)


def _fetch_performance_metrics() -> PerformanceMetrics:
    base_url = _normalise_base_url(REPORTS_BASE_URL)
    endpoint = urljoin(base_url, "reports/daily")
    try:
        response = httpx.get(endpoint, params={"limit": 30}, timeout=REPORTS_TIMEOUT_SECONDS)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Unable to retrieve performance metrics from %s: %s", endpoint, exc)
        return PerformanceMetrics(available=False)

    payload = response.json()
    if not isinstance(payload, list) or not payload:
        logger.info("Reports service returned no performance data from %s", endpoint)
        return PerformanceMetrics(available=False)

    ordered = sorted(
        (entry for entry in payload if isinstance(entry, dict)),
        key=lambda item: item.get("session_date", ""),
        reverse=True,
    )
    if not ordered:
        return PerformanceMetrics(available=False)

    latest = ordered[0]
    daily_pnls = [_coerce_float(entry.get("pnl")) for entry in ordered]
    returns, exposure_normalised = _compute_returns(ordered, daily_pnls)
    cumulative_return, cumulative_is_ratio = _compute_cumulative_return(returns, exposure_normalised)
    sharpe_ratio = _compute_sharpe(returns)

    max_drawdown = _coerce_float(latest.get("max_drawdown"))
    currency = (latest.get("currency") or latest.get("ccy") or "$")
    if isinstance(currency, str):
        currency_symbol = currency.strip() or "$"
    else:
        currency_symbol = "$"

    metrics = PerformanceMetrics(
        account=latest.get("account") if isinstance(latest.get("account"), str) else None,
        as_of=_parse_session_date(latest.get("session_date")),
        currency=currency_symbol,
        current_pnl=daily_pnls[0] if daily_pnls else 0.0,
        current_drawdown=max_drawdown,
        cumulative_return=cumulative_return,
        cumulative_return_is_ratio=cumulative_is_ratio,
        sharpe_ratio=sharpe_ratio,
        sample_size=len(ordered),
        uses_exposure=exposure_normalised,
        available=True,
    )
    return metrics


def _extract_strategy_identifiers(record: dict[str, object]) -> List[str]:
    identifiers: List[str] = []
    raw_id = record.get("id")
    if isinstance(raw_id, str) and raw_id:
        identifiers.append(raw_id)

    name = record.get("name")
    if isinstance(name, str) and name:
        identifiers.append(name)
        identifiers.append(name.lower())
        identifiers.append(name.replace(" ", "-").lower())

    metadata = record.get("metadata")
    if isinstance(metadata, dict):
        for key in ("strategy_id", "id", "slug"):
            value = metadata.get(key)
            if isinstance(value, str) and value:
                identifiers.append(value)

    tags = record.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, str) and tag:
                identifiers.append(tag)

    return [identifier for identifier in identifiers if identifier]


def _match_execution_for_strategy(
    identifiers: Sequence[str], executions: Sequence[dict[str, object]]
) -> dict[str, object] | None:
    if not identifiers or not executions:
        return None

    normalised = {identifier.lower() for identifier in identifiers if isinstance(identifier, str)}
    if not normalised:
        return None

    for execution in executions:
        if not isinstance(execution, dict):
            continue
        strategy_id = execution.get("strategy_id")
        if isinstance(strategy_id, str) and strategy_id.lower() in normalised:
            return execution
        metadata = execution.get("metadata")
        if isinstance(metadata, dict):
            tagged = metadata.get("strategy_id")
            if isinstance(tagged, str) and tagged.lower() in normalised:
                return execution
        tags = execution.get("tags")
        if isinstance(tags, list):
            for tag in tags:
                if not isinstance(tag, str):
                    continue
                if tag.startswith("strategy:"):
                    value = tag.split(":", 1)[1]
                    if value.lower() in normalised:
                        return execution
                if tag.lower() in normalised:
                    return execution
    return None


def _build_execution_snapshot(entry: dict[str, object]) -> StrategyExecutionSnapshot:
    submitted = _parse_timestamp(entry.get("submitted_at")) or _parse_timestamp(
        entry.get("created_at")
    )
    snapshot = StrategyExecutionSnapshot(
        order_id=str(entry.get("order_id")) if entry.get("order_id") is not None else None,
        status=str(entry.get("status")) if entry.get("status") is not None else None,
        submitted_at=submitted,
        symbol=str(entry.get("symbol")) if entry.get("symbol") is not None else None,
        venue=str(entry.get("venue")) if entry.get("venue") is not None else None,
        side=str(entry.get("side")) if entry.get("side") is not None else None,
        quantity=_coerce_optional_float(entry.get("quantity")),
        filled_quantity=_coerce_optional_float(entry.get("filled_quantity")),
    )
    return snapshot


def _build_strategy_statuses() -> tuple[List[StrategyStatus], List[LiveLogEntry]]:
    base_url = _normalise_base_url(ORCHESTRATOR_BASE_URL)
    endpoint = urljoin(base_url, "strategies")
    try:
        response = httpx.get(endpoint, timeout=ORCHESTRATOR_TIMEOUT_SECONDS)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Unable to retrieve strategies from %s: %s", endpoint, exc)
        return [], []

    payload = response.json()
    raw_items = payload.get("items") if isinstance(payload, dict) else None
    orchestrator_state = {}
    if isinstance(payload, dict):
        state = payload.get("orchestrator_state")
        if isinstance(state, dict):
            orchestrator_state = state

    executions_raw = orchestrator_state.get("recent_executions")
    executions: List[dict[str, object]] = []
    if isinstance(executions_raw, list):
        executions = [entry for entry in executions_raw if isinstance(entry, dict)]

    strategies: List[StrategyStatus] = []
    identifier_to_id: Dict[str, str] = {}

    if isinstance(raw_items, list):
        for record in raw_items:
            if not isinstance(record, dict):
                continue
            identifiers = _extract_strategy_identifiers(record)
            strategy_id = record.get("id")
            if not isinstance(strategy_id, str) or not strategy_id:
                metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
                if isinstance(metadata, dict):
                    candidate = metadata.get("strategy_id") or metadata.get("id")
                    if isinstance(candidate, str):
                        strategy_id = candidate
            strategy_id = strategy_id or ""

            for identifier in identifiers:
                identifier_to_id.setdefault(identifier.lower(), str(strategy_id))

            status_value = record.get("status")
            try:
                runtime_status = StrategyRuntimeStatus(status_value)
            except (ValueError, TypeError):
                runtime_status = StrategyRuntimeStatus.PENDING

            execution_entry = _match_execution_for_strategy(identifiers, executions)
            last_execution = _build_execution_snapshot(execution_entry) if execution_entry else None

            strategy = StrategyStatus(
                id=str(strategy_id),
                name=str(record.get("name")),
                status=runtime_status,
                enabled=bool(record.get("enabled")),
                strategy_type=(
                    str(record.get("strategy_type")) if record.get("strategy_type") is not None else None
                ),
                tags=[tag for tag in record.get("tags", []) if isinstance(tag, str)],
                last_error=(
                    str(record.get("last_error")) if record.get("last_error") is not None else None
                ),
                last_execution=last_execution,
                metadata=(record.get("metadata") if isinstance(record.get("metadata"), dict) else {}),
            )
            strategies.append(strategy)

    logs: List[LiveLogEntry] = []
    if executions:
        for entry in executions:
            timestamp = _parse_timestamp(entry.get("submitted_at")) or _parse_timestamp(
                entry.get("created_at")
            )
            if not timestamp:
                continue
            status = str(entry.get("status")) if entry.get("status") is not None else None
            symbol = str(entry.get("symbol")) if entry.get("symbol") is not None else None
            order_id = (
                str(entry.get("order_id")) if entry.get("order_id") is not None else None
            )

            tags = entry.get("tags")
            strategy_hint = None
            if isinstance(tags, list):
                for tag in tags:
                    if isinstance(tag, str) and tag.startswith("strategy:"):
                        strategy_hint = tag.split(":", 1)[1]
                        break

            strategy_id = None
            if strategy_hint:
                strategy_id = identifier_to_id.get(strategy_hint.lower())

            extra = {
                key: value
                for key, value in entry.items()
                if key
                not in {
                    "order_id",
                    "status",
                    "submitted_at",
                    "created_at",
                    "symbol",
                    "tags",
                }
            }

            message_parts = []
            if status:
                message_parts.append(status)
            if symbol:
                message_parts.append(str(symbol))
            if order_id:
                message_parts.append(f"(ordre {order_id})")
            if not message_parts:
                message_parts.append("Exécution enregistrée")

            logs.append(
                LiveLogEntry(
                    timestamp=timestamp,
                    message=" ".join(message_parts),
                    order_id=order_id,
                    status=status,
                    symbol=symbol,
                    strategy_id=strategy_id,
                    strategy_hint=strategy_hint,
                    extra=extra,
                )
            )

    logs.sort(key=lambda entry: entry.timestamp, reverse=True)
    if len(logs) > MAX_LOG_ENTRIES:
        logs = logs[:MAX_LOG_ENTRIES]

    return strategies, logs


def _build_portfolio_history(days: int = 30) -> List[PortfolioHistorySeries]:
    """Generate synthetic time series for each portfolio."""

    portfolios = _build_portfolios()
    if days < 2:
        days = 2

    now = datetime.utcnow()
    history: List[PortfolioHistorySeries] = []
    for index, portfolio in enumerate(portfolios):
        base_value = sum(holding.market_value for holding in portfolio.holdings)
        if not base_value:
            base_value = 1_000.0

        series: List[PortfolioTimeseriesPoint] = []
        for day in range(days):
            offset = days - day - 1
            timestamp = now - timedelta(days=offset)

            # Build a deterministic walk combining a smooth drift and oscillation.
            progress = day / (days - 1)
            seasonal = math.sin(progress * math.pi * 2 + index) * 0.015
            drift = 0.0025 * day
            noise = math.cos(progress * math.pi * 4 + index) * 0.005
            ratio = 1 + drift + seasonal + noise

            value = base_value * ratio
            pnl = value - base_value

            series.append(
                PortfolioTimeseriesPoint(
                    timestamp=timestamp.replace(microsecond=0),
                    value=round(value, 2),
                    pnl=round(pnl, 2),
                )
            )

        history.append(
            PortfolioHistorySeries(
                name=portfolio.name,
                owner=portfolio.owner,
                currency="$",
                series=series,
            )
        )

    return history


def load_dashboard_context() -> DashboardContext:
    """Return consistent sample data for the dashboard view."""

    strategies, logs = _build_strategy_statuses()
    return DashboardContext(
        portfolios=_build_portfolios(),
        transactions=_build_transactions(),
        alerts=_build_alerts(),
        metrics=_fetch_performance_metrics(),
        strategies=strategies,
        logs=logs,
    )


def load_portfolio_history() -> List[PortfolioHistorySeries]:
    """Expose synthetic portfolio history series for visualisation components."""

    return _build_portfolio_history()


__all__ = [
    "load_dashboard_context",
    "load_portfolio_history",
]

