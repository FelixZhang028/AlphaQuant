"""Holdout isolation and shared preprocessing regression coverage."""

from dataclasses import dataclass

import pandas as pd
import pytest

from quant_platform.application.factor_research_service import (
    BoundedRepository,
    research_combination,
)
from quant_platform.factors.base import FactorDefinition
from quant_platform.factors.combine import CompositeFactor, combine_factors, prepare_frames
from quant_platform.factors.evaluation import FactorEvaluator


@dataclass(frozen=True)
class TestFactor(FactorDefinition):
    __test__ = False

    def compute(self, bars):
        return bars.rename(columns={"trade_date": "date", self.name: "value"})[
            ["date", "symbol", "value"]
        ].copy()


class Repository:
    def __init__(self, bars):
        self.bars = bars

    def get_daily_bars(self, symbols=None, end_date=None):
        result = self.bars.copy()
        if end_date is not None:
            result = result[result.trade_date <= pd.Timestamp(end_date)]
        return result if symbols is None else result[result.symbol.isin(symbols)]


@pytest.fixture
def research_case():
    days = pd.bdate_range("2025-01-01", periods=50)
    bars = pd.DataFrame(
        [
            {
                "trade_date": day,
                "symbol": str(i),
                "raw_close": 100 * (1 + (i + 1) / 100) ** d,
                "positive": float(i),
                "negative": float(-i),
            }
            for d, day in enumerate(days)
            for i in range(10)
        ]
    )
    factors = (
        TestFactor(name="positive", display_name="正向"),
        TestFactor(name="negative", display_name="反向"),
    )
    config = dict(
        train_start=days[0].date(),
        train_end=days[24].date(),
        test_start=days[25].date(),
        test_end=days[-1].date(),
        horizon=1,
        n_groups=5,
        clip=True,
        missing="drop",
    )
    return Repository(bars), factors, config


def test_ic_weights_are_frozen_before_test_data(research_case):
    repo, factors, config = research_case
    first = research_combination(repo, factors, mode="ic", **config)
    assert first.weights == {"positive": 1.0, "negative": 0.0}
    changed = repo.bars.copy()
    mask = changed.trade_date >= pd.Timestamp(config["test_start"])
    changed.loc[mask, "raw_close"] = 1000 / changed.loc[mask, "raw_close"]
    changed.loc[mask, "positive"] *= -1
    second = research_combination(Repository(changed), factors, mode="ic", **config)
    assert second.weights == first.weights
    pd.testing.assert_frame_equal(second.correlation, first.correlation)


def test_training_return_labels_do_not_cross_boundary(research_case):
    repo, _, config = research_case
    bounded = BoundedRepository(repo, config["train_end"])
    labels = FactorEvaluator(bounded)._forward_returns(None, 5)
    dates = sorted(repo.bars.trade_date.unique())
    assert labels.date.max() == pd.Timestamp(dates[18])


def test_equal_baseline_and_custom_equal_match(research_case):
    repo, factors, config = research_case
    # Both candidates have the same direction to avoid a constant composite.
    factors = (factors[0], TestFactor(name="negative", display_name="反向", direction=-1))
    result = research_combination(repo, factors, mode="equal", **config)
    pd.testing.assert_frame_equal(
        result.reports["等权组合"].daily_ic, result.reports["我的组合"].daily_ic
    )
    assert len(result.comparison) == 4
    assert all(row["clip"] and row["missing"] == "drop" for row in result.spec)


def test_invalid_dates_and_weights_are_rejected(research_case):
    repo, factors, config = research_case
    with pytest.raises(ValueError, match="日期"):
        research_combination(repo, factors, **{**config, "test_start": config["train_end"]})
    for weights in ({}, {"positive": -1}, {"positive": float("nan")}):
        with pytest.raises(ValueError, match="权重"):
            research_combination(repo, factors, mode="manual", custom_weights=weights, **config)


@pytest.mark.parametrize("missing", ["drop", "median"])
def test_composite_applies_cleaning_to_actual_scores(research_case, missing):
    repo, factors, _ = research_case
    bars = repo.bars.iloc[:10].copy()
    bars.loc[bars.index[-1], "positive"] = 10000
    bars.loc[bars.index[0], "negative"] = float("nan")
    raw = {f.name: f.compute(bars) for f in factors}
    cleaned = prepare_frames(raw, clip=True, missing=missing)
    weights = {f.name: 0.5 for f in factors}
    expected = combine_factors(cleaned, weights, missing="drop")
    actual = CompositeFactor(
        components=factors, weights=weights, clip=True, missing=missing
    ).compute(bars)
    pd.testing.assert_frame_equal(actual, expected)
    assert len(actual) == (9 if missing == "drop" else 10)
    uncleaned = CompositeFactor(components=factors, weights=weights).compute(bars)
    assert not actual.equals(uncleaned)
