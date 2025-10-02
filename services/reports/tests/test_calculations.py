import pytest

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
