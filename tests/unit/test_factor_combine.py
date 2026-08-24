"""因子合成（combine）模块的单元测试。"""

from __future__ import annotations

import pandas as pd
import pytest

from quant_platform.factors.base import FactorDefinition
from quant_platform.factors.combine import (
    CompositeFactor,
    combine_factors,
    correlation_matrix,
    drop_highly_correlated,
)


def _frame(values: dict[str, float], dates: list[str] | None = None) -> pd.DataFrame:
    dates = dates or ["2024-01-02", "2024-01-03"]
    rows = [
        {"date": day, "symbol": symbol, "value": value}
        for day in dates
        for symbol, value in values.items()
    ]
    return pd.DataFrame(rows)


def test_combine_equal_weights_produces_zscore_average() -> None:
    a = _frame({"AAA": 1.0, "BBB": 2.0, "CCC": 3.0})
    b = _frame({"AAA": 3.0, "BBB": 2.0, "CCC": 1.0})
    combined = combine_factors({"a": a, "b": b}, {"a": 1.0, "b": 1.0})
    assert list(combined.columns) == ["date", "symbol", "value"]
    # 两个因子 z-score 后互为相反数，等权合成应恒为 0
    assert combined["value"].abs().max() == pytest.approx(0.0)


def test_combine_applies_direction_and_weight() -> None:
    a = _frame({"AAA": 0.0, "BBB": 1.0, "CCC": 2.0})
    # direction=-1 后 BBB 应排在 CCC 前面
    combined = combine_factors({"a": a}, {"a": 2.0}, directions={"a": -1})
    latest = combined[combined["date"] == combined["date"].max()]
    scores = dict(zip(latest["symbol"], latest["value"], strict=True))
    assert scores["BBB"] > scores["CCC"]


def test_combine_missing_factor_value_treated_as_zero() -> None:
    a = _frame({"AAA": 1.0, "BBB": 2.0, "CCC": 3.0})
    b = _frame({"AAA": 1.0, "BBB": 2.0, "CCC": 3.0}, dates=["2024-01-02"])
    combined = combine_factors({"a": a, "b": b}, {"a": 0.5, "b": 0.5})
    day2 = combined[combined["date"] == pd.Timestamp("2024-01-03")]
    assert len(day2) == 3  # b 在 1-03 缺失，不应导致整只票消失


def test_combine_rejects_unknown_weight_and_zero_total() -> None:
    a = _frame({"AAA": 1.0})
    with pytest.raises(ValueError, match="未提供"):
        combine_factors({"a": a}, {"ghost": 1.0})
    with pytest.raises(ValueError, match="权重之和"):
        combine_factors({"a": a}, {"a": 0.0})


def test_correlation_matrix_detects_identical_factors() -> None:
    a = _frame({"AAA": 1.0, "BBB": 2.0, "CCC": 3.0, "DDD": 4.0},
               dates=["2024-01-02", "2024-01-03", "2024-01-04"])
    b = a.copy()
    c = _frame({"AAA": 4.0, "BBB": 3.0, "CCC": 2.0, "DDD": 1.0},
               dates=["2024-01-02", "2024-01-03", "2024-01-04"])
    corr = correlation_matrix({"a": a, "b": b, "c": c})
    assert corr.loc["a", "b"] == pytest.approx(1.0)
    assert corr.loc["a", "c"] == pytest.approx(-1.0)


def test_drop_highly_correlated_respects_priority() -> None:
    corr = pd.DataFrame(
        [[1.0, 0.9, 0.1], [0.9, 1.0, 0.1], [0.1, 0.1, 1.0]],
        index=["a", "b", "c"],
        columns=["a", "b", "c"],
    )
    assert drop_highly_correlated(corr, threshold=0.7, priority=["b", "a", "c"]) == ["a"]
    assert drop_highly_correlated(corr, threshold=0.7) == ["b"]


class _ConstantFactor(FactorDefinition):
    def __init__(self, name: str, value: float, min_history: int = 5) -> None:
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "display_name", name)
        object.__setattr__(self, "min_history", min_history)
        object.__setattr__(self, "required_fields", ("adjusted_close",))
        object.__setattr__(self, "_value", value)

    def compute(self, bars: pd.DataFrame) -> pd.DataFrame:
        return _frame({"AAA": self._value, "BBB": -self._value})


def test_composite_factor_merges_metadata_and_computes() -> None:
    a = _ConstantFactor("fa", 1.0, min_history=10)
    b = _ConstantFactor("fb", 2.0, min_history=30)
    composite = CompositeFactor(
        name="combo",
        display_name="合成",
        components=(a, b),
        weights={"fa": 1.0, "fb": 1.0},
    )
    assert composite.min_history == 30
    assert composite.required_fields == ("adjusted_close",)
    result = composite.compute(pd.DataFrame())
    assert not result.empty


def test_composite_factor_rejects_empty_and_duplicate() -> None:
    with pytest.raises(ValueError, match="至少需要一个"):
        CompositeFactor(name="x", display_name="x", components=(), weights={})
    a = _ConstantFactor("fa", 1.0)
    with pytest.raises(ValueError, match="重复"):
        CompositeFactor(
            name="x", display_name="x", components=(a, a), weights={"fa": 1.0}
        )
