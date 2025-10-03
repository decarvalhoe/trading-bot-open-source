"""Sample data served by the web dashboard service."""

from __future__ import annotations

import logging
import json
import math
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from statistics import mean, stdev
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence
from urllib.parse import quote, urljoin

import httpx

from schemas.order_router import OrderRecord
from libs.portfolio import encode_portfolio_key, encode_position_key

from .order_router_client import OrderRouterClient, OrderRouterError
from .schemas import (
    Alert,
    AlertRuleDefinition,
    DashboardContext,
    FollowerCopySnapshot,
    FollowerDashboardContext,
    Holding,
    InPlayDashboardSetups,
    InPlaySetupStatus,
    InPlayStrategySetup,
    InPlaySymbolSetups,
    InPlayWatchlistSetups,
    LiveLogEntry,
    PerformanceMetrics,
    Portfolio,
    PortfolioHistorySeries,
    PortfolioTimeseriesPoint,
    RiskLevel,
    ReportListItem,
    StrategyExecutionSnapshot,
    StrategyRuntimeStatus,
    StrategyStatus,
    Transaction,
)


from .config import default_service_url


logger = logging.getLogger(__name__)

REPORTS_BASE_URL = os.getenv(
    "WEB_DASHBOARD_REPORTS_BASE_URL",
    default_service_url("http://reports:8000/", native_port=8016),
)
REPORTS_TIMEOUT_SECONDS = float(os.getenv("WEB_DASHBOARD_REPORTS_TIMEOUT", "5.0"))
ORCHESTRATOR_BASE_URL = os.getenv(
    "WEB_DASHBOARD_ORCHESTRATOR_BASE_URL",
    default_service_url("http://algo_engine:8000/", native_port=8014),
)
ORCHESTRATOR_TIMEOUT_SECONDS = float(os.getenv("WEB_DASHBOARD_ORCHESTRATOR_TIMEOUT", "5.0"))
MAX_LOG_ENTRIES = int(os.getenv("WEB_DASHBOARD_MAX_LOG_ENTRIES", "100"))
ALERT_ENGINE_BASE_URL = os.getenv(
    "WEB_DASHBOARD_ALERT_ENGINE_URL",
    default_service_url("http://alert_engine:8000/", native_port=8017),
)
ALERT_ENGINE_TIMEOUT_SECONDS = float(os.getenv("WEB_DASHBOARD_ALERT_ENGINE_TIMEOUT", "5.0"))
MAX_ALERTS = int(os.getenv("WEB_DASHBOARD_MAX_ALERTS", "20"))
INPLAY_BASE_URL = os.getenv("WEB_DASHBOARD_INPLAY_BASE_URL", "http://inplay:8000/")
INPLAY_TIMEOUT_SECONDS = float(os.getenv("WEB_DASHBOARD_INPLAY_TIMEOUT", "3.0"))
INPLAY_WATCHLISTS = [
    watchlist.strip()
    for watchlist in os.getenv("WEB_DASHBOARD_INPLAY_WATCHLISTS", "momentum").split(",")
    if watchlist.strip()
]
INPLAY_FALLBACK_MESSAGE = (
    "Instantané statique utilisé faute de connexion au service InPlay."
)
INPLAY_DEGRADED_MESSAGE = (
    "Flux InPlay partiellement disponible : certains instantanés proviennent du cache."
)

ORDER_ROUTER_BASE_URL = os.getenv(
    "WEB_DASHBOARD_ORDER_ROUTER_BASE_URL",
    default_service_url("http://order_router:8000/", native_port=8013),
)
ORDER_ROUTER_TIMEOUT_SECONDS = float(
    os.getenv("WEB_DASHBOARD_ORDER_ROUTER_TIMEOUT", "5.0")
)
ORDER_ROUTER_LOG_LIMIT = int(os.getenv("WEB_DASHBOARD_ORDER_LOG_LIMIT", "200"))
MAX_TRANSACTIONS = int(os.getenv("WEB_DASHBOARD_MAX_TRANSACTIONS", "25"))
MARKETPLACE_BASE_URL = os.getenv("WEB_DASHBOARD_MARKETPLACE_URL", "http://marketplace:8000/")
MARKETPLACE_TIMEOUT_SECONDS = float(os.getenv("WEB_DASHBOARD_MARKETPLACE_TIMEOUT", "5.0"))
FOLLOWER_FALLBACK_MESSAGE = (
    "Marketplace indisponible pour récupérer vos copies."
)


class MarketplaceServiceError(RuntimeError):
    """Raised when the marketplace service cannot fulfil a request."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        context: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.context = context or {}


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _fallback_portfolios() -> List[Portfolio]:
    growth_id = encode_portfolio_key("alice")
    income_id = encode_portfolio_key("bob")
    return [
        Portfolio(
            id=growth_id,
            name="Growth",
            owner="alice",
            holdings=[
                Holding(
                    id=encode_position_key("alice", "AAPL"),
                    symbol="AAPL",
                    quantity=12,
                    average_price=154.2,
                    current_price=178.4,
                    portfolio="alice",
                    portfolio_id=growth_id,
                ),
                Holding(
                    id=encode_position_key("alice", "MSFT"),
                    symbol="MSFT",
                    quantity=5,
                    average_price=298.1,
                    current_price=310.6,
                    portfolio="alice",
                    portfolio_id=growth_id,
                ),
            ],
        ),
        Portfolio(
            id=income_id,
            name="Income",
            owner="bob",
            holdings=[
                Holding(
                    id=encode_position_key("bob", "TLT"),
                    symbol="TLT",
                    quantity=20,
                    average_price=100.5,
                    current_price=98.2,
                    portfolio="bob",
                    portfolio_id=income_id,
                ),
                Holding(
                    id=encode_position_key("bob", "XOM"),
                    symbol="XOM",
                    quantity=15,
                    average_price=88.5,
                    current_price=105.7,
                    portfolio="bob",
                    portfolio_id=income_id,
                ),
            ],
        ),
    ]


def _fallback_transactions() -> List[Transaction]:
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


def _format_account_label(account_id: str) -> str:
    cleaned = (account_id or "").strip()
    if not cleaned:
        return "Portefeuille"
    normalised = cleaned.replace("_", " ").replace("-", " ")
    words = [segment for segment in normalised.split(" ") if segment]
    if not words:
        return cleaned
    return " ".join(word.capitalize() for word in words)


def _iter_order_fills(order: OrderRecord) -> Iterable[tuple[datetime | None, float, float]]:
    """Yield execution tuples (timestamp, price, quantity) for an order."""

    executions = sorted(
        order.executions,
        key=lambda execution: execution.executed_at
        or execution.created_at
        or order.updated_at
        or order.created_at,
    )
    emitted = False
    for execution in executions:
        quantity = _coerce_optional_float(execution.quantity)
        price = _coerce_optional_float(execution.price)
        if not quantity:
            continue
        emitted = True
        yield (
            execution.executed_at
            or execution.created_at
            or order.updated_at
            or order.created_at,
            price or 0.0,
            abs(quantity),
        )

    if emitted:
        return

    fallback_quantity = _coerce_optional_float(order.filled_quantity)
    if not fallback_quantity:
        return
    fallback_price = _coerce_optional_float(order.limit_price) or _coerce_optional_float(
        order.stop_price
    )
    yield (
        order.updated_at or order.submitted_at or order.created_at,
        fallback_price or 0.0,
        abs(fallback_quantity),
    )


def _build_portfolios_from_orders(orders: Sequence[OrderRecord]) -> List[Portfolio]:
    if not orders:
        return []

    positions: dict[str, dict[str, dict[str, float]]] = defaultdict(
        lambda: defaultdict(
            lambda: {
                "net_quantity": 0.0,
                "abs_quantity": 0.0,
                "abs_notional": 0.0,
                "last_price": 0.0,
            }
        )
    )

    for order in orders:
        account = (order.account_id or "").strip() or "default"
        symbol = (order.symbol or "").strip()
        if not symbol:
            continue
        side = (order.side or "buy").lower()
        direction = -1.0 if side.startswith("s") else 1.0
        for executed_at, price, quantity in _iter_order_fills(order):
            if not quantity:
                continue
            stats = positions[account][symbol]
            stats["net_quantity"] += quantity * direction
            stats["abs_quantity"] += quantity
            stats["abs_notional"] += quantity * (price or 0.0)
            if price:
                stats["last_price"] = price

    portfolios: List[Portfolio] = []
    for account, symbols in sorted(positions.items(), key=lambda item: item[0].lower()):
        holdings: List[Holding] = []
        portfolio_id = encode_portfolio_key(account)
        for symbol, stats in sorted(symbols.items(), key=lambda item: item[0]):
            quantity = stats["net_quantity"]
            total_traded = stats["abs_quantity"]
            if math.isclose(quantity, 0.0, abs_tol=1e-9):
                continue
            if math.isclose(total_traded, 0.0, abs_tol=1e-9):
                continue
            average_price = (
                stats["abs_notional"] / total_traded if total_traded else stats["last_price"]
            )
            current_price = stats["last_price"] or average_price or 0.0
            holdings.append(
                Holding(
                    id=encode_position_key(account, symbol),
                    symbol=symbol,
                    quantity=quantity,
                    average_price=average_price or 0.0,
                    current_price=current_price,
                    portfolio=account,
                    portfolio_id=portfolio_id,
                )
            )
        holdings.sort(key=lambda holding: holding.symbol)
        portfolios.append(
            Portfolio(
                id=portfolio_id,
                name=_format_account_label(account),
                owner=account,
                holdings=holdings,
            )
        )
    return portfolios


def _build_transactions_from_orders(orders: Sequence[OrderRecord]) -> List[Transaction]:
    if not orders:
        return []

    transactions: List[Transaction] = []
    for order in orders:
        account = (order.account_id or "").strip() or "default"
        symbol = (order.symbol or "").strip()
        if not symbol:
            continue
        side_raw = (order.side or "").lower()
        side = "sell" if side_raw.startswith("s") else "buy"
        for executed_at, price, quantity in _iter_order_fills(order):
            if not quantity:
                continue
            timestamp = executed_at or order.updated_at or order.created_at or datetime.utcnow()
            transactions.append(
                Transaction(
                    timestamp=timestamp,
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                    portfolio=account,
                )
            )

    transactions.sort(key=lambda txn: txn.timestamp, reverse=True)
    if len(transactions) > MAX_TRANSACTIONS:
        transactions = transactions[:MAX_TRANSACTIONS]
    return transactions


def _load_positions_snapshot() -> tuple[List[Portfolio], str]:
    base_url = _normalise_base_url(ORDER_ROUTER_BASE_URL)
    endpoint = urljoin(base_url, "positions")
    try:
        with OrderRouterClient(
            base_url=base_url, timeout=ORDER_ROUTER_TIMEOUT_SECONDS
        ) as client:
            snapshot = client.fetch_positions()
    except (httpx.HTTPError, OrderRouterError) as exc:
        logger.warning("Unable to retrieve positions from %s: %s", endpoint, exc)
        return _fallback_portfolios(), "fallback"
    except Exception as exc:  # pragma: no cover - defensive guard for unexpected errors
        logger.exception("Unexpected error while retrieving positions from %s: %s", endpoint, exc)
        return _fallback_portfolios(), "fallback"

    items = snapshot.items or []
    portfolios: List[Portfolio] = []
    for entry in items:
        holdings = [
            Holding(
                id=holding.id,
                symbol=holding.symbol,
                quantity=holding.quantity,
                average_price=holding.average_price,
                current_price=holding.current_price,
                portfolio=holding.portfolio or entry.owner,
                portfolio_id=holding.portfolio_id or entry.id,
            )
            for holding in entry.holdings
        ]
        portfolios.append(
            Portfolio(
                id=entry.id,
                name=entry.name,
                owner=entry.owner,
                holdings=holdings,
            )
        )
    return portfolios, "live"


def _load_order_log() -> tuple[List[OrderRecord], str]:
    base_url = _normalise_base_url(ORDER_ROUTER_BASE_URL)
    endpoint = urljoin(base_url, "orders/log")
    try:
        with OrderRouterClient(
            base_url=base_url, timeout=ORDER_ROUTER_TIMEOUT_SECONDS
        ) as client:
            snapshot = client.fetch_orders(limit=ORDER_ROUTER_LOG_LIMIT)
    except (httpx.HTTPError, OrderRouterError) as exc:
        logger.warning("Unable to retrieve orders from %s: %s", endpoint, exc)
        return [], "fallback"
    except Exception as exc:  # pragma: no cover - defensive guard for unexpected errors
        logger.exception("Unexpected error while retrieving orders from %s: %s", endpoint, exc)
        return [], "fallback"

    items = snapshot.items or []
    return items, "live"


def _fallback_alerts() -> List[Alert]:
    base_time = datetime.utcnow()
    return [
        Alert(
            id="maint-margin",
            title="Maintenance margin nearing threshold",
            detail="Portfolio Growth is at 82% of the allowed maintenance margin.",
            risk=RiskLevel.warning,
            created_at=base_time - timedelta(minutes=35),
            rule=AlertRuleDefinition(symbol="Growth", timeframe="1h"),
        ),
        Alert(
            id="drawdown",
            title="Daily drawdown limit exceeded",
            detail="Income portfolio dropped 6% over the last trading session.",
            risk=RiskLevel.critical,
            created_at=base_time - timedelta(hours=7),
            rule=AlertRuleDefinition(symbol="Income", timeframe="1d"),
        ),
        Alert(
            id="news",
            title="Breaking news on AAPL",
            detail="Apple announces quarterly earnings call for next Tuesday.",
            risk=RiskLevel.info,
            created_at=base_time - timedelta(hours=1, minutes=10),
            acknowledged=True,
            rule=AlertRuleDefinition(symbol="AAPL", timeframe="1h"),
        ),
    ]


def _map_severity_to_risk(severity: str | None) -> RiskLevel:
    if not severity:
        return RiskLevel.info
    lowered = severity.lower()
    if lowered in {"critical", "high", "severe"}:
        return RiskLevel.critical
    if lowered in {"warning", "medium", "moderate"}:
        return RiskLevel.warning
    return RiskLevel.info


def _format_alert_detail(entry: Dict[str, object], context: Dict[str, object]) -> str:
    symbol = entry.get("symbol") if isinstance(entry.get("symbol"), str) else ""
    components = []
    if symbol:
        components.append(f"Symbol {symbol}")
    price = context.get("price")
    if isinstance(price, (int, float)):
        components.append(f"price={price}")
    volume = context.get("volume")
    if isinstance(volume, (int, float)):
        components.append(f"volume={volume}")
    if context and not components:
        components.append(f"context={context}")
    if not components:
        return "Rule conditions matched the latest market snapshot."
    return "Rule conditions matched the latest market snapshot (" + ", ".join(components) + ")."


def _fetch_alerts_from_engine() -> List[Alert]:
    base_url = _normalise_base_url(ALERT_ENGINE_BASE_URL)
    endpoint = urljoin(base_url, "alerts")
    try:
        response = httpx.get(
            endpoint,
            params={"limit": MAX_ALERTS},
            timeout=ALERT_ENGINE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Falling back to static alerts because %s is unreachable: %s", endpoint, exc)
        return _fallback_alerts()

    payload = response.json()
    if not isinstance(payload, list):
        logger.warning("Alert engine returned unexpected payload: %s", payload)
        return _fallback_alerts()

    alerts: List[Alert] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        context = entry.get("context") if isinstance(entry.get("context"), dict) else {}
        triggered_at = _parse_timestamp(entry.get("triggered_at")) or datetime.utcnow()
        title = entry.get("name") if isinstance(entry.get("name"), str) else "Alert triggered"
        risk = _map_severity_to_risk(entry.get("severity") if isinstance(entry.get("severity"), str) else None)
        alerts.append(
            Alert(
                id=str(entry.get("trigger_id", title)),
                title=title,
                detail=_format_alert_detail(entry, context),
                risk=risk,
                created_at=triggered_at,
                acknowledged=False,
            )
        )

    return alerts or _fallback_alerts()


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


def _coerce_int(value: object, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _format_report_type(value: object) -> str:
    if not isinstance(value, str):
        return "Rapport personnalisé"
    cleaned = value.replace("_", " ").strip()
    if not cleaned:
        return "Rapport personnalisé"
    return cleaned[:1].upper() + cleaned[1:]


def _format_period_range(start: datetime | None, end: datetime | None) -> str | None:
    if start and end:
        if start.date() == end.date():
            return start.strftime("%d/%m/%Y")
        return f"{start.strftime('%d/%m/%Y')} → {end.strftime('%d/%m/%Y')}"
    if start:
        return f"Depuis le {start.strftime('%d/%m/%Y')}"
    if end:
        return f"Jusqu'au {end.strftime('%d/%m/%Y')}"
    return None


def _extract_period_from_parameters(parameters: object) -> str | None:
    if not isinstance(parameters, dict):
        return None
    start = parameters.get("start_date") or parameters.get("start") or parameters.get("from")
    end = parameters.get("end_date") or parameters.get("end") or parameters.get("to")
    start_dt = _parse_timestamp(start)
    end_dt = _parse_timestamp(end)
    period = _format_period_range(start_dt, end_dt)
    if period:
        return period
    timeframe = parameters.get("timeframe") or parameters.get("window") or parameters.get("period")
    if isinstance(timeframe, str) and timeframe.strip():
        label = timeframe.replace("_", " ").strip()
        return label[:1].upper() + label[1:]
    return None


def _normalise_report_entry(payload: dict[str, object], base_url: str) -> ReportListItem | None:
    parameters = payload.get("parameters") if isinstance(payload.get("parameters"), dict) else {}
    report_type = _format_report_type(
        (parameters or {}).get("report_type")
        or payload.get("type")
        or payload.get("name")
    )
    generated_at = (
        _parse_timestamp(payload.get("completed_at"))
        or _parse_timestamp(payload.get("updated_at"))
        or _parse_timestamp(payload.get("created_at"))
    )
    period = _extract_period_from_parameters(parameters)
    resource = payload.get("resource")
    download_url: str | None = None
    filename: str | None = None
    if isinstance(resource, str) and resource.strip():
        download_url = resource if resource.startswith("http") else urljoin(base_url, resource.lstrip("/"))
        filename = Path(resource).name or None
    identifier = payload.get("id")
    if not download_url and isinstance(identifier, (str, int)):
        download_url = urljoin(base_url, f"reports/jobs/{quote(str(identifier))}")
    status = payload.get("status") if isinstance(payload.get("status"), str) else None
    return ReportListItem(
        id=str(identifier) if isinstance(identifier, (str, int)) else None,
        report_type=report_type,
        period=period,
        generated_at=generated_at,
        download_url=download_url,
        filename=filename,
        status=status,
        source="jobs",
    )


def _map_jobs_payload(payload: object, base_url: str) -> List[ReportListItem]:
    items: List[ReportListItem] = []
    entries: object
    if isinstance(payload, dict):
        entries = payload.get("items") or payload.get("jobs") or []
    else:
        entries = payload
    if not isinstance(entries, list):
        return items
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        report = _normalise_report_entry(entry, base_url)
        if report:
            items.append(report)
    return items


def _map_performance_payload(payload: object, base_url: str) -> List[ReportListItem]:
    entries: object = payload
    if isinstance(payload, dict):
        entries = payload.get("items") or payload.get("reports") or []
    if not isinstance(entries, list):
        return []
    items: List[ReportListItem] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        account = entry.get("account") if isinstance(entry.get("account"), str) else None
        start_dt = _parse_timestamp(entry.get("start_date") or entry.get("start"))
        end_dt = _parse_timestamp(entry.get("end_date") or entry.get("end"))
        period = _format_period_range(start_dt, end_dt)
        generated_at = end_dt or _parse_timestamp(entry.get("as_of"))
        slug = (account or "global").strip().lower().replace(" ", "-")
        filename = f"performance-{slug}.csv"
        query = "reports/performance?export=csv"
        if account:
            query += f"&account={quote(account)}"
        download_url = urljoin(base_url, query)
        report_type = "Performance portefeuille"
        if account:
            report_type = f"{report_type} · {account}"
        items.append(
            ReportListItem(
                id=account or None,
                report_type=report_type,
                period=period,
                generated_at=generated_at,
                download_url=download_url,
                filename=filename,
                status=None,
                source="performance",
            )
        )
    return items


def _normalise_inplay_status(value: object) -> InPlaySetupStatus:
    if isinstance(value, InPlaySetupStatus):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == InPlaySetupStatus.validated.value:
            return InPlaySetupStatus.validated
        if lowered == InPlaySetupStatus.failed.value:
            return InPlaySetupStatus.failed
    return InPlaySetupStatus.pending


def _normalise_inplay_strategy(entry: dict[str, object]) -> InPlayStrategySetup | None:
    if not isinstance(entry, dict):
        return None

    raw_strategy = entry.get("strategy") or entry.get("name")
    if not isinstance(raw_strategy, str) or not raw_strategy.strip():
        return None
    strategy = raw_strategy.strip()

    status = _normalise_inplay_status(entry.get("status"))
    entry_level = _coerce_optional_float(entry.get("entry"))
    target_level = _coerce_optional_float(entry.get("target"))
    stop_level = _coerce_optional_float(entry.get("stop"))
    probability = _coerce_optional_float(entry.get("probability"))
    if probability is not None:
        probability = max(0.0, min(1.0, probability))

    updated_at = _parse_timestamp(entry.get("updated_at") or entry.get("received_at"))
    raw_session = (
        entry.get("session")
        or entry.get("session_name")
        or entry.get("sessionName")
        or entry.get("market")
        or None
    )
    session: str | None = None
    if isinstance(raw_session, str) and raw_session.strip():
        session = raw_session.strip().lower().replace(" ", "_")

    report_url = entry.get("report_url") or entry.get("reportUrl")
    if isinstance(report_url, str) and report_url.strip():
        report_url = report_url.strip()
    else:
        report_url = None

    return InPlayStrategySetup(
        strategy=strategy,
        status=status,
        entry=entry_level,
        target=target_level,
        stop=stop_level,
        probability=probability,
        updated_at=updated_at,
        session=session,
        report_url=report_url,
    )


def _normalise_inplay_symbol(entry: dict[str, object]) -> InPlaySymbolSetups | None:
    if not isinstance(entry, dict):
        return None

    raw_symbol = entry.get("symbol") or entry.get("ticker")
    if not isinstance(raw_symbol, str) or not raw_symbol.strip():
        return None
    symbol = raw_symbol.strip()

    raw_setups = entry.get("setups")
    if not isinstance(raw_setups, list):
        raw_setups = []

    setups: List[InPlayStrategySetup] = []
    for item in raw_setups:
        normalised = _normalise_inplay_strategy(item)
        if normalised:
            if not normalised.report_url:
                encoded_symbol = quote(symbol, safe="")
                encoded_strategy = quote(normalised.strategy, safe="")
                normalised.report_url = f"/inplay/setups/{encoded_symbol}/{encoded_strategy}"
            setups.append(normalised)

    return InPlaySymbolSetups(symbol=symbol, setups=setups)


def _normalise_inplay_watchlist(
    payload: dict[str, object], default_id: str | None = None
) -> InPlayWatchlistSetups | None:
    if not isinstance(payload, dict):
        return None

    raw_id = payload.get("id") or payload.get("watchlist_id") or default_id
    if not isinstance(raw_id, str) or not raw_id.strip():
        return None
    watchlist_id = raw_id.strip()

    raw_symbols = payload.get("symbols")
    if not isinstance(raw_symbols, list):
        raw_symbols = []

    symbols: List[InPlaySymbolSetups] = []
    for entry in raw_symbols:
        normalised = _normalise_inplay_symbol(entry)
        if normalised:
            symbols.append(normalised)

    return InPlayWatchlistSetups(
        id=watchlist_id,
        symbols=symbols,
        updated_at=_parse_timestamp(payload.get("updated_at")),
    )


def _fallback_inplay_setups() -> InPlayDashboardSetups:
    base_time = datetime.utcnow()
    return InPlayDashboardSetups(
        watchlists=[
            InPlayWatchlistSetups(
                id="demo-momentum",
                updated_at=base_time,
                symbols=[
                    InPlaySymbolSetups(
                        symbol="AAPL",
                        setups=[
                            InPlayStrategySetup(
                                strategy="ORB",
                                status=InPlaySetupStatus.pending,
                                entry=189.95,
                                target=192.1,
                                stop=187.8,
                                probability=0.64,
                                updated_at=base_time,
                                session="london",
                                report_url="/inplay/setups/AAPL/ORB",
                            )
                        ],
                    ),
                    InPlaySymbolSetups(
                        symbol="MSFT",
                        setups=[
                            InPlayStrategySetup(
                                strategy="Breakout",
                                status=InPlaySetupStatus.validated,
                                entry=404.2,
                                target=409.5,
                                stop=398.7,
                                probability=0.58,
                                updated_at=base_time,
                                session="new_york",
                                report_url="/inplay/setups/MSFT/Breakout",
                            )
                        ],
                    ),
                ],
            )
        ],
        fallback_reason=INPLAY_FALLBACK_MESSAGE,
    )


def _fetch_inplay_setups() -> InPlayDashboardSetups:
    watchlists: List[InPlayWatchlistSetups] = []
    errors_detected = False

    configured = INPLAY_WATCHLISTS or ["momentum"]
    base_url = _normalise_base_url(INPLAY_BASE_URL)

    for watchlist_id in configured:
        endpoint = urljoin(base_url, f"inplay/watchlists/{watchlist_id}")
        try:
            response = httpx.get(endpoint, timeout=INPLAY_TIMEOUT_SECONDS)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                "Impossible de récupérer la watchlist InPlay %s depuis %s: %s",
                watchlist_id,
                endpoint,
                exc,
            )
            errors_detected = True
            continue

        payload = response.json()
        snapshot = _normalise_inplay_watchlist(payload, default_id=watchlist_id)
        if snapshot is None:
            logger.warning(
                "Payload InPlay inattendu pour la watchlist %s: %s",
                watchlist_id,
                payload,
            )
            errors_detected = True
            continue

        watchlists.append(snapshot)

    if not watchlists:
        return _fallback_inplay_setups()

    setups = InPlayDashboardSetups(watchlists=watchlists)
    if errors_detected:
        setups.fallback_reason = INPLAY_DEGRADED_MESSAGE
    return setups


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


def load_reports_list() -> List[ReportListItem]:
    """Retrieve available reports or export jobs from the reports service."""

    base_url = _normalise_base_url(REPORTS_BASE_URL)
    endpoints = [
        ("reports/jobs", _map_jobs_payload),
        ("reports/performance", _map_performance_payload),
    ]

    for path, mapper in endpoints:
        endpoint = urljoin(base_url, path)
        try:
            response = httpx.get(endpoint, timeout=REPORTS_TIMEOUT_SECONDS)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                logger.info("Reports endpoint %s not available: %s", endpoint, exc)
            else:
                logger.warning("Unable to load reports from %s: %s", endpoint, exc)
            continue
        except httpx.HTTPError as exc:
            logger.warning("Unable to reach reports endpoint %s: %s", endpoint, exc)
            continue

        try:
            payload = response.json()
        except ValueError:
            logger.warning("Malformed JSON payload received from %s", endpoint)
            continue

        items = mapper(payload, base_url)
        if not items:
            continue

        ordered = sorted(
            items,
            key=lambda report: report.generated_at or datetime.min,
            reverse=True,
        )
        return ordered

    return []


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
    id_to_name: Dict[str, str] = {}
    raw_records: List[dict[str, object]] = []

    if isinstance(raw_items, list):
        for record in raw_items:
            if not isinstance(record, dict):
                continue
            raw_records.append(record)
            strategy_id_value = record.get("id")
            if isinstance(strategy_id_value, str) and strategy_id_value:
                name_value = record.get("name")
                id_to_name[strategy_id_value] = (
                    str(name_value) if name_value is not None else strategy_id_value
                )

    for record in raw_records:
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

        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        parent_id = record.get("derived_from")
        if not isinstance(parent_id, str) or not parent_id:
            parent_id = metadata.get("derived_from") if isinstance(metadata, dict) else None
            if not isinstance(parent_id, str):
                parent_id = None

        parent_name = record.get("derived_from_name")
        if not isinstance(parent_name, str) and parent_id:
            parent_name = id_to_name.get(parent_id)
            if not parent_name and isinstance(metadata, dict):
                candidate_name = metadata.get("derived_from_name") or metadata.get("parent_name")
                if isinstance(candidate_name, str):
                    parent_name = candidate_name

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
            metadata=metadata if isinstance(metadata, dict) else {},
            derived_from=parent_id,
            derived_from_name=parent_name if isinstance(parent_name, str) else None,
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

    portfolios = _fallback_portfolios()
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
    portfolios, portfolios_mode = _load_positions_snapshot()
    orders, orders_mode = _load_order_log()

    if portfolios_mode != "live" and orders_mode == "live":
        portfolios = _build_portfolios_from_orders(orders)
        portfolios_mode = orders_mode

    if not portfolios and portfolios_mode != "live":
        portfolios = _fallback_portfolios()
        portfolios_mode = "fallback"

    if orders_mode == "live":
        transactions = _build_transactions_from_orders(orders)
    else:
        transactions = _fallback_transactions()

    data_sources = {
        "portfolios": portfolios_mode,
        "transactions": orders_mode if orders_mode == "live" else "fallback",
    }
    return DashboardContext(
        portfolios=portfolios,
        transactions=transactions,
        alerts=_fetch_alerts_from_engine(),
        metrics=_fetch_performance_metrics(),
        reports=load_reports_list(),
        strategies=strategies,
        logs=logs,
        setups=_fetch_inplay_setups(),
        data_sources=data_sources,
    )


def load_follower_dashboard(viewer_id: str) -> FollowerDashboardContext:
    """Retrieve copy-trading subscriptions for the follower dashboard."""

    base_url = _normalise_base_url(MARKETPLACE_BASE_URL)
    endpoint = urljoin(base_url, "marketplace/copies")
    headers = {"x-user-id": viewer_id}
    try:
        response = httpx.get(
            endpoint,
            headers=headers,
            timeout=MARKETPLACE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning(
            "Unable to load copy subscriptions for %s: %s", viewer_id, exc
        )
        return FollowerDashboardContext(
            viewer_id=viewer_id,
            source="fallback",
            fallback_reason=FOLLOWER_FALLBACK_MESSAGE,
        )

    try:
        payload = response.json()
    except ValueError:
        logger.warning("Marketplace returned invalid JSON for copies endpoint")
        return FollowerDashboardContext(
            viewer_id=viewer_id,
            source="fallback",
            fallback_reason="Réponse marketplace invalide.",
        )

    snapshots: List[FollowerCopySnapshot] = []
    if isinstance(payload, list):
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            listing_id = entry.get("listing_id")
            if not isinstance(listing_id, int):
                continue
            strategy_name = entry.get("strategy_name")
            leader_id = entry.get("leader_id")
            leverage_raw = entry.get("leverage", 1.0)
            try:
                leverage = float(leverage_raw)
            except (TypeError, ValueError):
                leverage = 1.0
            allocated_raw = entry.get("allocated_capital")
            try:
                allocated = float(allocated_raw) if allocated_raw is not None else None
            except (TypeError, ValueError):
                allocated = None
            risk_limits = entry.get("risk_limits")
            if not isinstance(risk_limits, dict):
                risk_limits = {}
            divergence = entry.get("divergence_bps")
            try:
                divergence_value = (
                    float(divergence) if divergence is not None else None
                )
            except (TypeError, ValueError):
                divergence_value = None
            fees = entry.get("total_fees_paid") or entry.get("estimated_fees")
            try:
                fees_value = float(fees) if fees is not None else 0.0
            except (TypeError, ValueError):
                fees_value = 0.0
            status = entry.get("replication_status") or entry.get("status") or "idle"
            last_synced = _parse_timestamp(entry.get("last_synced_at"))
            snapshots.append(
                FollowerCopySnapshot(
                    listing_id=listing_id,
                    strategy_name=str(strategy_name)
                    if isinstance(strategy_name, str)
                    else None,
                    leader_id=str(leader_id) if isinstance(leader_id, str) else None,
                    leverage=leverage,
                    allocated_capital=allocated,
                    risk_limits=risk_limits,
                    divergence_bps=divergence_value,
                    estimated_fees=fees_value,
                    replication_status=str(status),
                    last_synced_at=last_synced,
                )
            )

    return FollowerDashboardContext(copies=snapshots, viewer_id=viewer_id)


def _build_marketplace_url(path: str) -> str:
    base_url = _normalise_base_url(MARKETPLACE_BASE_URL)
    clean_path = path.lstrip("/")
    return urljoin(base_url, clean_path)


def _extract_marketplace_error_payload(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError:
        return response.text


def _build_marketplace_error(
    *,
    message: str,
    status_code: int | None = None,
    url: str | None = None,
    payload: object | None = None,
) -> MarketplaceServiceError:
    context: dict[str, object] = {}
    if url:
        context["url"] = url
    if payload is not None:
        context["payload"] = payload
    if status_code is not None:
        context["status_code"] = status_code
    return MarketplaceServiceError(message, status_code=status_code, context=context)


def _interpret_marketplace_error(
    response: httpx.Response, *, url: str
) -> MarketplaceServiceError:
    payload = _extract_marketplace_error_payload(response)
    message = "Erreur renvoyée par le service marketplace."
    if isinstance(payload, dict):
        for key in ("detail", "message", "error"):
            candidate = payload.get(key)
            if isinstance(candidate, str) and candidate.strip():
                message = candidate.strip()
                break
    elif isinstance(payload, str) and payload.strip():
        message = payload.strip()
    return _build_marketplace_error(
        message=message, status_code=response.status_code, url=url, payload=payload
    )


async def _request_marketplace_json(
    path: str, *, params: Mapping[str, object] | None = None
) -> object:
    url = _build_marketplace_url(path)
    query_params = {
        key: value
        for key, value in (params or {}).items()
        if value not in (None, "")
    }
    try:
        async with httpx.AsyncClient(timeout=MARKETPLACE_TIMEOUT_SECONDS) as client:
            response = await client.get(
                url,
                params=query_params or None,
                headers={"Accept": "application/json"},
            )
    except httpx.TimeoutException as exc:
        message = "La marketplace n'a pas répondu dans le délai imparti."
        raise _build_marketplace_error(
            message=message,
            url=url,
            payload={"timeout_seconds": MARKETPLACE_TIMEOUT_SECONDS},
        ) from exc
    except httpx.HTTPError as exc:
        message = "Impossible de contacter le service marketplace."
        raise _build_marketplace_error(
            message=message,
            url=url,
            payload={"error": str(exc)},
        ) from exc

    if response.status_code >= 400:
        raise _interpret_marketplace_error(response, url=url)

    try:
        return response.json()
    except ValueError as exc:
        message = "Réponse JSON invalide reçue depuis la marketplace."
        raise _build_marketplace_error(message=message, url=url) from exc


def _derive_price_cents(entry: Mapping[str, Any]) -> int:
    raw_price = entry.get("price_cents")
    if raw_price is not None:
        try:
            return max(0, int(round(float(raw_price))))
        except (TypeError, ValueError):
            pass
    for key in ("price_usd", "price", "monthly_price", "amount"):
        candidate = entry.get(key)
        if candidate is None:
            continue
        try:
            value = float(candidate)
        except (TypeError, ValueError):
            continue
        cents = int(round(value * 100))
        if cents >= 0:
            return cents
    return 0


def _normalise_currency(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip().upper()
    return "USD"


def _normalise_listing_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    listing_id = entry.get("id", entry.get("listing_id"))
    listing_id_int = _coerce_int(listing_id, default=0)

    owner_value = (
        entry.get("owner_id")
        or entry.get("leader_id")
        or entry.get("owner")
        or entry.get("creator_id")
    )
    owner_id = str(owner_value).strip() if owner_value not in (None, "") else "inconnu"

    strategy_name = entry.get("strategy_name") or entry.get("name")
    if not isinstance(strategy_name, str) or not strategy_name.strip():
        strategy_name = "Stratégie sans nom"
    else:
        strategy_name = strategy_name.strip()

    description = entry.get("description")
    if not isinstance(description, str) or not description.strip():
        description = None
    else:
        description = description.strip()

    raw_reviews = entry.get("reviews")
    if isinstance(raw_reviews, list):
        computed_count = len(raw_reviews)
        computed_average = [
            _coerce_optional_float(item.get("rating"))
            for item in raw_reviews
            if isinstance(item, Mapping)
        ]
        ratings = [value for value in computed_average if value is not None]
        average_from_reviews = (
            round(sum(ratings) / len(ratings), 2) if ratings else None
        )
    else:
        computed_count = 0
        average_from_reviews = None

    reviews_count = entry.get("reviews_count")
    reviews_count_int = _coerce_int(reviews_count, default=computed_count)
    if reviews_count_int == 0 and computed_count:
        reviews_count_int = computed_count

    average_rating = (
        _coerce_optional_float(entry.get("average_rating") or entry.get("rating"))
        or average_from_reviews
    )
    if average_rating is not None:
        average_rating = round(float(average_rating), 2)

    performance_score = _coerce_optional_float(
        entry.get("performance_score") or entry.get("performance")
    )
    risk_score = _coerce_optional_float(entry.get("risk_score") or entry.get("risk"))

    return {
        "id": listing_id_int,
        "strategy_name": strategy_name,
        "owner_id": owner_id,
        "price_cents": _derive_price_cents(entry),
        "currency": _normalise_currency(entry.get("currency")),
        "description": description,
        "performance_score": performance_score,
        "risk_score": risk_score,
        "average_rating": average_rating,
        "reviews_count": reviews_count_int,
    }


def _format_timestamp_for_response(timestamp: datetime | None) -> str:
    if timestamp is None:
        return _EPOCH.isoformat()
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc).isoformat()


def _normalise_review_entry(
    entry: Mapping[str, Any], *, listing_id: int, index: int
) -> dict[str, Any]:
    review_identifier = (
        entry.get("id")
        or entry.get("review_id")
        or entry.get("uuid")
        or entry.get("reference")
    )
    if review_identifier in (None, ""):
        review_identifier = f"review-{listing_id}-{index}"
    review_id = str(review_identifier)

    raw_rating = entry.get("rating") or entry.get("score")
    rating_value = _coerce_optional_float(raw_rating)
    if rating_value is None:
        rating_value = 0.0
    rating_value = min(5.0, max(0.0, float(rating_value)))
    rating_value = round(rating_value, 2)

    comment = entry.get("comment") or entry.get("body") or entry.get("content")
    if isinstance(comment, str):
        comment = comment.strip() or None
    else:
        comment = None

    reviewer = entry.get("reviewer_id") or entry.get("user_id") or entry.get("author_id")
    reviewer_id = str(reviewer).strip() if reviewer not in (None, "") else None

    timestamp = (
        entry.get("created_at")
        or entry.get("createdAt")
        or entry.get("submitted_at")
        or entry.get("timestamp")
    )
    parsed_timestamp = _parse_timestamp(timestamp)

    return {
        "id": review_id,
        "listing_id": listing_id,
        "rating": rating_value,
        "comment": comment,
        "created_at": _format_timestamp_for_response(parsed_timestamp),
        "reviewer_id": reviewer_id,
    }


async def fetch_marketplace_listings(
    filters: Mapping[str, object] | None = None,
) -> list[dict[str, Any]]:
    payload = await _request_marketplace_json(
        "marketplace/listings", params=filters or {}
    )
    items: list[Any]
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        for key in ("items", "results", "data"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                items = candidate
                break
        else:
            items = []
    else:
        items = []

    listings: list[dict[str, Any]] = []
    for entry in items:
        if isinstance(entry, Mapping):
            listings.append(_normalise_listing_entry(entry))
    return listings


async def fetch_marketplace_reviews(listing_id: int) -> list[dict[str, Any]]:
    payload = await _request_marketplace_json(
        f"marketplace/listings/{listing_id}/reviews"
    )
    items: list[Any]
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        for key in ("items", "results", "data"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                items = candidate
                break
        else:
            items = []
    else:
        items = []

    reviews: list[dict[str, Any]] = []
    for index, entry in enumerate(items):
        if isinstance(entry, Mapping):
            reviews.append(
                _normalise_review_entry(entry, listing_id=listing_id, index=index)
            )
    return reviews


def load_portfolio_history() -> List[PortfolioHistorySeries]:
    """Expose synthetic portfolio history series for visualisation components."""

    return _build_portfolio_history()


def _get_tradingview_storage_path() -> Path:
    """Return the path where the TradingView configuration is persisted."""

    raw_path = os.getenv("WEB_DASHBOARD_TRADINGVIEW_STORAGE")
    if raw_path:
        try:
            return Path(raw_path)
        except (TypeError, ValueError):  # pragma: no cover - defensive guard
            logger.warning("Invalid storage path provided for TradingView configuration: %s", raw_path)
    base_dir = os.getenv("WEB_DASHBOARD_DATA_DIR")
    if base_dir:
        return Path(base_dir) / "tradingview_config.json"
    return Path(__file__).resolve().parent / "tradingview_config.json"


def _load_tradingview_storage() -> dict[str, object]:
    """Read the persisted TradingView configuration from disk."""

    path = _get_tradingview_storage_path()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
            if isinstance(payload, dict):
                return payload
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("Unable to load TradingView configuration from %s: %s", path, error)
    return {}


def _dump_tradingview_storage(payload: dict[str, object]) -> None:
    """Persist the TradingView configuration to disk."""

    path = _get_tradingview_storage_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
    except OSError as error:  # pragma: no cover - unexpected filesystem failure
        logger.error("Unable to persist TradingView configuration to %s: %s", path, error)


def _parse_symbol_map(raw_value: str | None) -> dict[str, str]:
    """Normalise a symbol mapping provided via environment variables."""

    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON provided for WEB_DASHBOARD_TRADINGVIEW_SYMBOL_MAP")
        return {}
    if not isinstance(parsed, dict):
        return {}
    normalised: dict[str, str] = {}
    for key, value in parsed.items():
        if isinstance(key, str) and isinstance(value, str):
            normalised[key] = value
    return normalised


def _normalise_symbol_map(raw_mapping: dict[str, object] | None) -> dict[str, str]:
    """Ensure symbol mappings only include string keys and values."""

    if not isinstance(raw_mapping, dict):
        return {}
    normalised: dict[str, str] = {}
    for key, value in raw_mapping.items():
        if isinstance(key, str) and isinstance(value, str) and key.strip() and value.strip():
            normalised[key.strip()] = value.strip()
    return normalised


def load_tradingview_config() -> dict[str, object]:
    """Expose the TradingView configuration combining persisted data and environment fallbacks."""

    storage = _load_tradingview_storage()
    env_symbol_map = _parse_symbol_map(os.getenv("WEB_DASHBOARD_TRADINGVIEW_SYMBOL_MAP"))

    stored_symbol_map = _normalise_symbol_map(storage.get("symbol_map") if isinstance(storage, dict) else None)
    overlays = storage.get("overlays") if isinstance(storage, dict) else []
    if not isinstance(overlays, list):
        overlays = []
    filtered_overlays: list[dict[str, object]] = []
    for overlay in overlays:
        if isinstance(overlay, dict) and overlay.get("id") and overlay.get("title"):
            filtered_overlays.append(overlay)

    config = {
        "api_key": "",
        "library_url": "https://unpkg.com/@tradingview/charting_library@latest/charting_library/charting_library.js",
        "default_symbol": "BINANCE:BTCUSDT",
        "symbol_map": {},
        "overlays": filtered_overlays,
    }

    if isinstance(storage, dict):
        if isinstance(storage.get("api_key"), str):
            config["api_key"] = storage.get("api_key") or ""
        if isinstance(storage.get("library_url"), str) and storage.get("library_url").strip():
            config["library_url"] = storage.get("library_url")
        if isinstance(storage.get("default_symbol"), str) and storage.get("default_symbol").strip():
            config["default_symbol"] = storage.get("default_symbol")
    if stored_symbol_map:
        config["symbol_map"] = stored_symbol_map
    elif env_symbol_map:
        config["symbol_map"] = env_symbol_map

    api_key = os.getenv("WEB_DASHBOARD_TRADINGVIEW_API_KEY")
    if api_key:
        config["api_key"] = api_key

    library_url = os.getenv("WEB_DASHBOARD_TRADINGVIEW_LIBRARY_URL")
    if library_url:
        config["library_url"] = library_url

    default_symbol = os.getenv("WEB_DASHBOARD_TRADINGVIEW_DEFAULT_SYMBOL")
    if default_symbol:
        config["default_symbol"] = default_symbol

    return config


def save_tradingview_config(config: dict[str, object]) -> dict[str, object]:
    """Persist a sanitized TradingView configuration and return the stored payload."""

    storage: dict[str, object] = {}
    if isinstance(config, dict):
        api_key = config.get("api_key")
        library_url = config.get("library_url")
        default_symbol = config.get("default_symbol")
        symbol_map = config.get("symbol_map")
        overlays = config.get("overlays")

        if isinstance(api_key, str):
            storage["api_key"] = api_key.strip()
        else:
            storage["api_key"] = ""

        if isinstance(library_url, str) and library_url.strip():
            storage["library_url"] = library_url.strip()

        if isinstance(default_symbol, str) and default_symbol.strip():
            storage["default_symbol"] = default_symbol.strip()

        storage["symbol_map"] = _normalise_symbol_map(symbol_map if isinstance(symbol_map, dict) else None)

        serialised_overlays: list[dict[str, object]] = []
        if isinstance(overlays, list):
            for overlay in overlays:
                if not isinstance(overlay, dict):
                    continue
                overlay_id = overlay.get("id")
                title = overlay.get("title")
                if not isinstance(overlay_id, str) or not overlay_id.strip():
                    continue
                if not isinstance(title, str) or not title.strip():
                    continue
                entry = {
                    "id": overlay_id.strip(),
                    "title": title.strip(),
                    "type": overlay.get("type", "indicator"),
                    "settings": overlay.get("settings") if isinstance(overlay.get("settings"), dict) else {},
                }
                serialised_overlays.append(entry)
        storage["overlays"] = serialised_overlays

    _dump_tradingview_storage(storage)
    return storage


__all__ = [
    "load_dashboard_context",
    "load_portfolio_history",
    "load_reports_list",
    "load_tradingview_config",
    "save_tradingview_config",
]

