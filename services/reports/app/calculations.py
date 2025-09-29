from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date, datetime
from io import StringIO
from statistics import mean, pstdev
from typing import Iterable, List, Sequence

from sqlalchemy import select
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

from .tables import ReportDaily, ReportIntraday, ReportSnapshot


class ReportCalculator:
    def __init__(self, session: Session):
        self._session = session

    def _rows_for_timeframe(self, symbol: str, timeframe: Timeframe) -> Iterable[ReportDaily | ReportIntraday]:
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

    def _build_section(
        self,
        symbol: str,
        timeframe: Timeframe,
    ) -> ReportSection | None:
        rows = list(self._rows_for_timeframe(symbol, timeframe))
        if not rows:
            return None

        grouped: dict[StrategyName, list[ReportDaily | ReportIntraday]] = defaultdict(list)
        for row in rows:
            grouped[row.strategy].append(row)

        strategies: list[StrategyMetrics] = []
        for strategy in StrategyName:
            bucket = grouped.get(strategy, [])
            if not bucket:
                continue
            outcomes = [item.outcome for item in bucket]
            expectancy_values = [item.pnl for item in bucket]
            targets = [item.target_price for item in bucket]
            stops = [item.stop_price for item in bucket]
            metrics = StrategyMetrics(
                strategy=strategy,
                probability=self._success_ratio(outcomes),
                target=mean(targets),
                stop=mean(stops),
                expectancy=mean(expectancy_values),
                sample_size=len(bucket),
            )
            strategies.append(metrics)

        if not strategies:
            return None

        updated_at = max((row.created_at for row in rows), default=datetime.utcnow())
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
    rows = list(
        session.scalars(select(ReportSnapshot).where(ReportSnapshot.symbol == symbol))
    )
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

    def _fetch_rows(self, account: str | None) -> list[ReportDaily]:
        statement = select(ReportDaily)
        if account:
            statement = statement.where(ReportDaily.account == account)
        statement = statement.order_by(ReportDaily.account, ReportDaily.session_date, ReportDaily.id)
        return list(self._session.scalars(statement))

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

    def generate(self, account: str | None = None, limit: int | None = 30) -> List[DailyRiskReport]:
        rows = self._fetch_rows(account)
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

    def performance(self, account: str | None = None) -> list[PortfolioPerformance]:
        rows = self._fetch_rows(account)
        if not rows:
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
            daily_returns = [sum(row.pnl for row in per_day[session_date]) for session_date in ordered_dates]
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

            performance = PortfolioPerformance(
                account=account_id,
                start_date=ordered_dates[0],
                end_date=ordered_dates[-1],
                total_return=cumulative_return,
                cumulative_return=cumulative_return,
                average_return=average_return,
                volatility=volatility,
                sharpe_ratio=sharpe_ratio,
                max_drawdown=max_drawdown,
                observation_count=len(daily_returns),
                positive_days=sum(1 for value in daily_returns if value > 0),
                negative_days=sum(1 for value in daily_returns if value < 0),
            )
            performances.append(performance)

        performances.sort(key=lambda item: (item.account, item.start_date or date.min))
        return performances

    @staticmethod
    def export_csv(reports: Sequence[DailyRiskReport]) -> str:
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["session_date", "account", "pnl", "max_drawdown", "incidents"])
        for report in reports:
            incident_notes = ";".join(
                f"{incident.symbol}:{incident.strategy.value}:{incident.outcome.value}" for incident in report.incidents
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
