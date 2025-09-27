from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import mean
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from schemas.report import ReportResponse, ReportSection, StrategyMetrics, StrategyName, Timeframe

from .tables import Outcome, ReportDaily, ReportIntraday, ReportSnapshot


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
    def _success_ratio(outcomes: list[Outcome]) -> float:
        if not outcomes:
            return 0.0
        wins = sum(1 for outcome in outcomes if outcome is Outcome.WIN)
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
