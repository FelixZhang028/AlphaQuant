"""因子未来收益与训练/测试区间划分测试。"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from quant_platform.factors.base import FactorDefinition
from quant_platform.factors.evaluation import (
    FactorEvaluator,
    chronological_train_test_split,
)


def _repository(prices: list[float]) -> SimpleNamespace:
    bars = pd.DataFrame(
        {
            "trade_date": pd.date_range("2024-01-01", periods=len(prices)),
            "symbol": ["AAA"] * len(prices),
            "adjusted_close": prices,
        }
    )
    return SimpleNamespace(get_daily_bars=lambda symbols=None: bars.copy())


class _Repository:
    def __init__(self, bars: pd.DataFrame) -> None:
        self.bars = bars

    def get_daily_bars(
        self,
        symbols: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pd.DataFrame:
        frame = self.bars.copy()
        if symbols:
            frame = frame[frame["symbol"].isin(symbols)]
        if start_date:
            frame = frame[frame["trade_date"] >= pd.Timestamp(start_date)]
        if end_date:
            frame = frame[frame["trade_date"] <= pd.Timestamp(end_date)]
        return frame


class _PriceLevelFactor(FactorDefinition):
    name = "price_level"
    display_name = "价格水平"
    required_fields = ("adjusted_close",)

    def compute(self, bars: pd.DataFrame) -> pd.DataFrame:
        return bars[["trade_date", "symbol", "adjusted_close"]].rename(
            columns={"trade_date": "date", "adjusted_close": "value"}
        )


def test_one_day_forward_return_holds_one_complete_trading_day() -> None:
    evaluator = FactorEvaluator(_repository([100.0, 101.0, 103.0, 106.0]))

    result = evaluator._forward_returns(None, horizon=1)

    assert list(result["date"]) == list(pd.date_range("2024-01-01", periods=2))
    assert result.iloc[0]["fwd_ret"] == pytest.approx(103.0 / 101.0 - 1.0)
    assert result.iloc[1]["fwd_ret"] == pytest.approx(106.0 / 103.0 - 1.0)


def test_five_day_forward_return_exits_at_t_plus_six() -> None:
    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 111.0]
    evaluator = FactorEvaluator(_repository(prices))

    result = evaluator._forward_returns(None, horizon=5)

    assert len(result) == 1
    assert result.iloc[0]["fwd_ret"] == pytest.approx(111.0 / 101.0 - 1.0)


def test_chronological_split_uses_non_overlapping_trading_dates() -> None:
    dates = pd.date_range("2024-01-01", periods=10)

    train_end, test_start = chronological_train_test_split(dates)

    assert train_end.isoformat() == "2024-01-07"
    assert test_start.isoformat() == "2024-01-08"


def test_complete_evaluation_builds_turnover_for_adjacent_dates() -> None:
    dates = pd.date_range("2024-01-01", periods=10)
    rows = []
    for symbol_index in range(5):
        for day_index, trade_date in enumerate(dates):
            rows.append(
                {
                    "trade_date": trade_date,
                    "symbol": f"S{symbol_index}",
                    "adjusted_close": (10.0 + symbol_index)
                    * (1.0 + 0.001 * (symbol_index + 1)) ** day_index,
                }
            )
    evaluator = FactorEvaluator(_Repository(pd.DataFrame(rows)))

    report = evaluator.evaluate(
        _PriceLevelFactor(),
        date(2024, 1, 1),
        date(2024, 1, 7),
        horizon=1,
        n_groups=5,
    )

    assert not report.daily_ic.empty
    assert len(report.turnover) == 6
