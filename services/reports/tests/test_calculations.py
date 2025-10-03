import pytest
from unittest.mock import MagicMock

from schemas.report import StrategyMetrics, StrategyName
from services.reports.app.calculations import ReportCalculator


def test_merge_metrics_weights_target_and_stop() -> None:
    first = StrategyMetrics(
        strategy=StrategyName.ORB,
        probability=0.25,
        target=2.0,
        stop=1.0,
        expectancy=0.5,
        sample_size=10,
    )
    second = StrategyMetrics(
        strategy=StrategyName.ORB,
        probability=0.75,
        target=4.0,
        stop=2.0,
        expectancy=1.5,
        sample_size=30,
    )

    merged = ReportCalculator._merge_metrics(first, second)

    assert merged.target == pytest.approx(3.5)
    assert merged.stop == pytest.approx(1.75)


def test_merge_metrics_uses_present_dataset_when_other_empty() -> None:
    first = StrategyMetrics(
        strategy=StrategyName.ORB,
        probability=0.0,
        target=0.0,
        stop=0.0,
        expectancy=0.0,
        sample_size=0,
    )
    second = StrategyMetrics(
        strategy=StrategyName.ORB,
        probability=0.75,
        target=4.0,
        stop=2.0,
        expectancy=1.5,
        sample_size=30,
    )

    merged = ReportCalculator._merge_metrics(first, second)

    assert merged.target == pytest.approx(4.0)
    assert merged.stop == pytest.approx(2.0)


def test_merge_metrics_preserves_live_price_levels_when_backtest_missing_levels() -> None:
    live = StrategyMetrics(
        strategy=StrategyName.ORB,
        probability=0.6,
        target=101.5,
        stop=99.25,
        expectancy=0.8,
        sample_size=5,
    )
    backtest = StrategyMetrics(
        strategy=StrategyName.ORB,
        probability=0.4,
        target=None,
        stop=None,
        expectancy=0.5,
        sample_size=20,
    )

    merged = ReportCalculator._merge_metrics(live, backtest)

    assert merged.target == pytest.approx(live.target)
    assert merged.stop == pytest.approx(live.stop)


def test_metrics_from_backtest_omits_target_and_stop_levels() -> None:
    class StubBacktest:
        strategy_type = "ORB"
        strategy_name = "ORB"
        symbol = "AAPL"
        trades = 10
        total_return = 0.1
        initial_balance = 10000.0
        equity_curve = [10000.0, 10050.0, 10025.0, 10080.0]
        context = {"report_strategy": "ORB"}

    calculator = ReportCalculator(session=MagicMock())
    metrics = calculator._metrics_from_backtest(StubBacktest())

    assert metrics is not None
    assert metrics.target is None
    assert metrics.stop is None
