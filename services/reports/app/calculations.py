from __future__ import annotations

import csv
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from io import StringIO
from statistics import mean, pstdev
from typing import Iterable, List, Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from schemas.report import (
    DailyRiskIncident,
    DailyRiskReport,
    PortfolioPerformance,
    ReportResponse,
    ReportSection,
    StrategyMetrics,
    StrategyName,
    Timeframe,
    TradeOutcome,
)

from .tables import ReportBacktest, ReportBenchmark, ReportDaily, ReportIntraday, ReportSnapshot


def _normalise_strategy(value: str | None) -> str | None:
    if not value:
        return None
    return "".join(ch for ch in value.lower() if ch.isalnum()) or None


_STRATEGY_LOOKUP = {
    key: item
    for item in StrategyName
    for key in {_normalise_strategy(item.value), _normalise_strategy(item.name)}
    if key
}


class ReportCalculator:
    def __init__(self, session: Session):
        self._session = session

    def _rows_for_timeframe(
        self, symbol: str, timeframe: Timeframe
    ) -> Iterable[ReportDaily | ReportIntraday]:
        if timeframe is Timeframe.DAILY:
            statement = select(ReportDaily).where(ReportDaily.symbol == symbol)
        else:
            statement = select(ReportIntraday).where(ReportIntraday.symbol == symbol)
        return self._session.scalars(statement)

    @staticmethod
    def _success_ratio(outcomes: list[TradeOutcome]) -> float:
        if not outcomes:
            return 0.0
        wins = sum(1 for outcome in outcomes if outcome is TradeOutcome.WIN)
        return wins / len(outcomes)

    def _load_backtests(self, symbol: str) -> list[ReportBacktest]:
        statement = select(ReportBacktest).where(ReportBacktest.symbol == symbol)
        return list(self._session.scalars(statement))

    @staticmethod
    def _resolve_strategy_name(*values: str | None) -> StrategyName | None:
        for value in values:
            key = _normalise_strategy(value)
            if key and key in _STRATEGY_LOOKUP:
                return _STRATEGY_LOOKUP[key]
        return None

    def _metrics_from_backtest(self, row: ReportBacktest) -> StrategyMetrics | None:
        metadata = row.context if isinstance(row.context, dict) else {}
        strategy = self._resolve_strategy_name(
            row.strategy_type,
            row.strategy_name,
            metadata.get("report_strategy"),
        )
        if strategy is None:
            return None

        equity_curve = [float(value) for value in row.equity_curve or []]
        returns = [current - previous for previous, current in zip(equity_curve, equity_curve[1:])]
        wins = [value for value in returns if value > 0]
        losses = [value for value in returns if value < 0]
        sample_size = max(row.trades, len(returns)) or 1
        expectancy = mean(returns) if returns else row.total_return * row.initial_balance
        probability = len(wins) / len(returns) if returns else 0.0
        return StrategyMetrics(
            strategy=strategy,
            probability=probability,
            target=None,
            stop=None,
            expectancy=expectancy,
            sample_size=sample_size,
        )

    @staticmethod
    def _merge_metrics(first: StrategyMetrics, second: StrategyMetrics) -> StrategyMetrics:
        total_samples = first.sample_size + second.sample_size
        if total_samples <= 0:
            return first

        def _weighted(a: float, b: float) -> float:
            return (a * first.sample_size + b * second.sample_size) / total_samples

        def _merge_level(
            first_value: float | None, second_value: float | None
        ) -> float | None:
            if first_value is None and second_value is None:
                return None
            if first_value is None:
                return second_value
            if second_value is None:
                return first_value
            return _weighted(first_value, second_value)

        probability = _weighted(first.probability, second.probability)
        expectancy = _weighted(first.expectancy, second.expectancy)
        target = _merge_level(first.target, second.target)
        stop = _merge_level(first.stop, second.stop)

        return StrategyMetrics(
            strategy=first.strategy,
            probability=probability,
            target=target,
            stop=stop,
            expectancy=expectancy,
            sample_size=total_samples,
        )

    def _build_section(
        self,
        symbol: str,
        timeframe: Timeframe,
    ) -> ReportSection | None:
        rows = list(self._rows_for_timeframe(symbol, timeframe))
        metrics_map: dict[StrategyName, StrategyMetrics] = {}

        grouped: dict[StrategyName, list[ReportDaily | ReportIntraday]] = defaultdict(list)
        for row in rows:
            grouped[row.strategy].append(row)

        for strategy in StrategyName:
            bucket = grouped.get(strategy, [])
            if not bucket:
                continue
            outcomes = [item.outcome for item in bucket]
            expectancy_values = [item.pnl for item in bucket]
            targets = [item.target_price for item in bucket]
            stops = [item.stop_price for item in bucket]
            metrics_map[strategy] = StrategyMetrics(
                strategy=strategy,
                probability=self._success_ratio(outcomes),
                target=mean(targets),
                stop=mean(stops),
                expectancy=mean(expectancy_values),
                sample_size=len(bucket),
            )

        backtests: list[ReportBacktest] = []
        if timeframe is Timeframe.DAILY:
            backtests = self._load_backtests(symbol)
            for backtest in backtests:
                metrics = self._metrics_from_backtest(backtest)
                if metrics is None:
                    continue
                if metrics.strategy in metrics_map:
                    metrics_map[metrics.strategy] = self._merge_metrics(
                        metrics_map[metrics.strategy], metrics
                    )
                else:
                    metrics_map[metrics.strategy] = metrics

        if not metrics_map:
            return None

        updated_candidates = [row.created_at for row in rows]
        if timeframe is Timeframe.DAILY:
            updated_candidates.extend(backtest.created_at for backtest in backtests)
        updated_at = max(updated_candidates, default=datetime.utcnow())
        strategies = [metrics_map[name] for name in StrategyName if name in metrics_map]
        return ReportSection(timeframe=timeframe, strategies=strategies, updated_at=updated_at)

    def build_report(self, symbol: str) -> ReportResponse:
        daily = self._build_section(symbol, Timeframe.DAILY)
        intraday = self._build_section(symbol, Timeframe.INTRADAY)
        return ReportResponse(symbol=symbol, daily=daily, intraday=intraday)

    def persist_snapshot(self, symbol: str) -> ReportResponse:
        report = self.build_report(symbol)
        sections = [section for section in (report.daily, report.intraday) if section]
        for section in sections:
            for metrics in section.strategies:
                if metrics.target is None or metrics.stop is None:
                    continue
                snapshot = ReportSnapshot(
                    symbol=symbol,
                    timeframe=section.timeframe,
                    strategy=metrics.strategy,
                    probability=metrics.probability,
                    target=metrics.target,
                    stop=metrics.stop,
                    expectancy=metrics.expectancy,
                    sample_size=metrics.sample_size,
                    updated_at=section.updated_at or datetime.utcnow(),
                )
                self._session.merge(snapshot)
        self._session.flush()
        return report


def load_report_from_snapshots(session: Session, symbol: str) -> ReportResponse | None:
    rows = list(session.scalars(select(ReportSnapshot).where(ReportSnapshot.symbol == symbol)))
    if not rows:
        return None

    grouped: dict[Timeframe, list[ReportSnapshot]] = defaultdict(list)
    for row in rows:
        grouped[row.timeframe].append(row)

    sections: dict[Timeframe, ReportSection] = {}
    for timeframe, snapshots in grouped.items():
        strategies = [
            StrategyMetrics(
                strategy=snapshot.strategy,
                probability=snapshot.probability,
                target=snapshot.target,
                stop=snapshot.stop,
                expectancy=snapshot.expectancy,
                sample_size=snapshot.sample_size,
            )
            for snapshot in snapshots
        ]
        sections[timeframe] = ReportSection(
            timeframe=timeframe,
            strategies=strategies,
            updated_at=max(snapshot.updated_at for snapshot in snapshots),
        )

    return ReportResponse(
        symbol=symbol,
        daily=sections.get(Timeframe.DAILY),
        intraday=sections.get(Timeframe.INTRADAY),
    )


class DailyRiskCalculator:
    """Aggregate daily P&L, drawdown and incident metadata."""

    def __init__(self, session: Session):
        self._session = session

    def _fetch_rows(self, account: str | None, symbol: str | None = None) -> list[ReportDaily]:
        statement = select(ReportDaily)
        if account:
            statement = statement.where(ReportDaily.account == account)
        if symbol:
            statement = statement.where(ReportDaily.symbol == symbol)
        statement = statement.order_by(
            ReportDaily.account, ReportDaily.session_date, ReportDaily.id
        )
        return list(self._session.scalars(statement))

    def _fetch_backtests(
        self,
        account: str | None,
        symbol: str | None = None,
    ) -> list[ReportBacktest]:
        statement = select(ReportBacktest)
        if account:
            statement = statement.where(ReportBacktest.account == account)
        if symbol:
            statement = statement.where(ReportBacktest.symbol == symbol)
        statement = statement.order_by(ReportBacktest.created_at.desc())
        return list(self._session.scalars(statement))

    @staticmethod
    def _backtest_account(row: ReportBacktest) -> str:
        if row.account:
            return row.account
        if row.strategy_name:
            return f"backtest:{row.strategy_name}"
        return f"backtest:{row.strategy_id}"

    @staticmethod
    def _max_drawdown_value(equity_curve: Sequence[float]) -> float:
        if not equity_curve:
            return 0.0
        peak = equity_curve[0]
        max_drawdown = 0.0
        for value in equity_curve:
            peak = max(peak, value)
            max_drawdown = max(max_drawdown, peak - value)
        return max_drawdown

    def _convert_backtests(self, rows: Sequence[ReportBacktest]) -> List[DailyRiskReport]:
        reports: list[DailyRiskReport] = []
        for row in rows:
            equity_curve = [float(value) for value in row.equity_curve or []]
            pnl = (
                equity_curve[-1] - equity_curve[0]
                if len(equity_curve) >= 2
                else row.total_return * row.initial_balance
            )
            reports.append(
                DailyRiskReport(
                    session_date=row.created_at.date(),
                    account=self._backtest_account(row),
                    pnl=pnl,
                    max_drawdown=self._max_drawdown_value(equity_curve),
                    incidents=[],
                )
            )
        return reports

    @staticmethod
    def _incidents(rows: Sequence[ReportDaily]) -> list[DailyRiskIncident]:
        incidents: list[DailyRiskIncident] = []
        for row in rows:
            if row.outcome is not TradeOutcome.LOSS:
                continue
            incidents.append(
                DailyRiskIncident(
                    symbol=row.symbol,
                    strategy=row.strategy,
                    pnl=row.pnl,
                    outcome=row.outcome,
                    note="Loss recorded against stop or target",
                )
            )
        return incidents

    def _aggregate(self, rows: Sequence[ReportDaily], limit: int | None) -> List[DailyRiskReport]:
        if not rows:
            return []
        grouped: dict[str, dict[date, list[ReportDaily]]] = defaultdict(dict)
        for row in rows:
            bucket = grouped.setdefault(row.account, {}).setdefault(row.session_date, [])
            bucket.append(row)

        summaries: list[DailyRiskReport] = []
        for account_id, per_day in grouped.items():
            ordered_dates = sorted(per_day.keys())
            cumulative = 0.0
            peak_equity = 0.0
            max_drawdown_so_far = 0.0
            drawdown_by_date: dict[date, float] = {}
            for session_date in ordered_dates:
                day_rows = per_day[session_date]
                day_pnl = sum(row.pnl for row in day_rows)
                cumulative += day_pnl
                peak_equity = max(peak_equity, cumulative)
                current_drawdown = max(0.0, peak_equity - cumulative)
                max_drawdown_so_far = max(max_drawdown_so_far, current_drawdown)
                drawdown_by_date[session_date] = max_drawdown_so_far

            for session_date in ordered_dates:
                day_rows = per_day[session_date]
                summaries.append(
                    DailyRiskReport(
                        session_date=session_date,
                        account=account_id,
                        pnl=sum(row.pnl for row in day_rows),
                        max_drawdown=drawdown_by_date[session_date],
                        incidents=self._incidents(day_rows),
                    )
                )

        summaries.sort(key=lambda report: (report.session_date, report.account), reverse=True)
        if limit is not None and limit > 0:
            summaries = summaries[:limit]
        return summaries

    def generate(self, account: str | None = None, limit: int | None = 30) -> List[DailyRiskReport]:
        rows = self._fetch_rows(account)
        backtests = self._fetch_backtests(account)
        combined = self._aggregate(rows, None)
        combined.extend(self._convert_backtests(backtests))
        combined.sort(key=lambda report: (report.session_date, report.account), reverse=True)
        if limit is not None and limit > 0:
            combined = combined[:limit]
        return combined

    def generate_for_symbol(
        self,
        symbol: str,
        account: str | None = None,
        limit: int | None = 30,
    ) -> List[DailyRiskReport]:
        rows = self._fetch_rows(account, symbol)
        backtests = self._fetch_backtests(account, symbol)
        combined = self._aggregate(rows, None)
        combined.extend(self._convert_backtests(backtests))
        combined.sort(key=lambda report: (report.session_date, report.account), reverse=True)
        if limit is not None and limit > 0:
            combined = combined[:limit]
        return combined

    def _load_benchmarks(self, account: str | None, dates: Sequence[date]) -> dict[date, float]:
        if not dates:
            return {}

        statement = select(ReportBenchmark).where(ReportBenchmark.session_date.in_(dates))
        if account:
            statement = statement.where(
                or_(ReportBenchmark.account == account, ReportBenchmark.account.is_(None))
            )
        rows = list(self._session.scalars(statement))
        if not rows:
            return {}

        benchmarks: dict[date, float] = {}
        for row in rows:
            if account:
                if row.account == account:
                    benchmarks[row.session_date] = row.return_value
                elif row.account is None and row.session_date not in benchmarks:
                    benchmarks[row.session_date] = row.return_value
            else:
                if row.account is None:
                    benchmarks[row.session_date] = row.return_value
                elif row.session_date not in benchmarks:
                    benchmarks[row.session_date] = row.return_value
        return benchmarks

    @staticmethod
    def _compute_sortino(returns: Sequence[float]) -> float:
        if not returns:
            return 0.0

        average_return = mean(returns)
        downside = [min(0.0, value) for value in returns]
        downside_squared = [value**2 for value in downside if value < 0]
        if not downside_squared:
            return 0.0

        downside_deviation = math.sqrt(sum(downside_squared) / len(returns))
        if downside_deviation == 0:
            return 0.0
        return average_return / downside_deviation

    @staticmethod
    def _compute_alpha_beta(
        portfolio_returns: Sequence[float], benchmark_returns: Sequence[float]
    ) -> tuple[float, float]:
        if len(portfolio_returns) < 2 or len(benchmark_returns) < 2:
            return 0.0, 0.0

        portfolio_mean = mean(portfolio_returns)
        benchmark_mean = mean(benchmark_returns)
        benchmark_variance = sum(
            (value - benchmark_mean) ** 2 for value in benchmark_returns
        ) / len(benchmark_returns)
        if benchmark_variance == 0:
            return 0.0, 0.0

        covariance = sum(
            (port - portfolio_mean) * (bench - benchmark_mean)
            for port, bench in zip(portfolio_returns, benchmark_returns)
        ) / len(portfolio_returns)
        beta = covariance / benchmark_variance
        alpha = portfolio_mean - beta * benchmark_mean
        return alpha, beta

    @staticmethod
    def _compute_tracking_error(
        portfolio_returns: Sequence[float], benchmark_returns: Sequence[float]
    ) -> float:
        if len(portfolio_returns) < 2 or len(benchmark_returns) < 2:
            return 0.0

        differences = [port - bench for port, bench in zip(portfolio_returns, benchmark_returns)]
        variance = sum(diff**2 for diff in differences) / len(differences)
        return math.sqrt(variance)

    def performance(self, account: str | None = None) -> list[PortfolioPerformance]:
        rows = self._fetch_rows(account)
        backtests = self._fetch_backtests(account)
        if not rows and not backtests:
            return []

        grouped: dict[str, dict[date, list[ReportDaily]]] = defaultdict(dict)
        for row in rows:
            bucket = grouped.setdefault(row.account, {}).setdefault(row.session_date, [])
            bucket.append(row)

        performances: list[PortfolioPerformance] = []
        for account_id, per_day in grouped.items():
            ordered_dates = sorted(per_day.keys())
            if not ordered_dates:
                continue
            daily_returns_by_date = {
                session_date: sum(row.pnl for row in per_day[session_date])
                for session_date in ordered_dates
            }
            daily_returns = [daily_returns_by_date[session_date] for session_date in ordered_dates]
            if not daily_returns:
                continue

            cumulative_return = 0.0
            peak_equity = 0.0
            max_drawdown = 0.0
            for day_return in daily_returns:
                cumulative_return += day_return
                peak_equity = max(peak_equity, cumulative_return)
                drawdown = max(0.0, peak_equity - cumulative_return)
                max_drawdown = max(max_drawdown, drawdown)

            average_return = mean(daily_returns)
            volatility = pstdev(daily_returns) if len(daily_returns) > 1 else 0.0
            sharpe_ratio = average_return / volatility if volatility > 0 else 0.0

            benchmark_series = self._load_benchmarks(account_id, ordered_dates)
            overlapping_dates = [day for day in ordered_dates if day in benchmark_series]
            benchmark_returns = [benchmark_series[day] for day in overlapping_dates]
            portfolio_returns = [daily_returns_by_date[day] for day in overlapping_dates]
            alpha, beta = self._compute_alpha_beta(portfolio_returns, benchmark_returns)
            tracking_error = self._compute_tracking_error(portfolio_returns, benchmark_returns)
            sortino_ratio = self._compute_sortino(daily_returns)

            performance = PortfolioPerformance(
                account=account_id,
                start_date=ordered_dates[0],
                end_date=ordered_dates[-1],
                total_return=cumulative_return,
                cumulative_return=cumulative_return,
                average_return=average_return,
                volatility=volatility,
                sharpe_ratio=sharpe_ratio,
                sortino_ratio=sortino_ratio,
                alpha=alpha,
                beta=beta,
                tracking_error=tracking_error,
                max_drawdown=max_drawdown,
                observation_count=len(daily_returns),
                positive_days=sum(1 for value in daily_returns if value > 0),
                negative_days=sum(1 for value in daily_returns if value < 0),
            )
            performances.append(performance)

        performances.extend(self._build_backtest_performance(backtests))
        performances.sort(key=lambda item: (item.account, item.start_date or date.min))
        return performances

    def _build_backtest_performance(
        self, rows: Sequence[ReportBacktest]
    ) -> list[PortfolioPerformance]:
        performances: list[PortfolioPerformance] = []
        for row in rows:
            equity_curve = [float(value) for value in row.equity_curve or []]
            returns = [
                current - previous for previous, current in zip(equity_curve, equity_curve[1:])
            ]
            cumulative_return = (
                equity_curve[-1] - equity_curve[0]
                if len(equity_curve) >= 2
                else row.total_return * row.initial_balance
            )
            average_return = mean(returns) if returns else 0.0
            volatility = pstdev(returns) if len(returns) > 1 else 0.0
            sharpe_ratio = average_return / volatility if volatility > 0 else 0.0
            sortino_ratio = self._compute_sortino(returns)
            observation_count = len(returns)
            positive_days = sum(1 for value in returns if value > 0)
            negative_days = sum(1 for value in returns if value < 0)
            start_date = (
                row.created_at.date() - timedelta(days=observation_count - 1)
                if observation_count > 0
                else row.created_at.date()
            )
            performances.append(
                PortfolioPerformance(
                    account=self._backtest_account(row),
                    start_date=start_date,
                    end_date=row.created_at.date(),
                    total_return=cumulative_return,
                    cumulative_return=cumulative_return,
                    average_return=average_return,
                    volatility=volatility,
                    sharpe_ratio=sharpe_ratio,
                    sortino_ratio=sortino_ratio,
                    alpha=0.0,
                    beta=0.0,
                    tracking_error=0.0,
                    max_drawdown=self._max_drawdown_value(equity_curve),
                    observation_count=observation_count,
                    positive_days=positive_days,
                    negative_days=negative_days,
                )
            )
        return performances

    @staticmethod
    def export_csv(reports: Sequence[DailyRiskReport]) -> str:
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["session_date", "account", "pnl", "max_drawdown", "incidents"])
        for report in reports:
            incident_notes = ";".join(
                f"{incident.symbol}:{incident.strategy.value}:{incident.outcome.value}"
                for incident in report.incidents
            )
            writer.writerow(
                [
                    report.session_date.isoformat(),
                    report.account,
                    f"{report.pnl:.2f}",
                    f"{report.max_drawdown:.2f}",
                    incident_notes,
                ]
            )
        buffer.seek(0)
        return buffer.getvalue()
