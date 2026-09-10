"""引擎级除权估值测试：分红、送转、缺复权因子回退与未复权对照。"""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from quant_platform.backtest.engine import BacktestEngine
from quant_platform.execution.next_open import ExecutionConfig, NextOpenExecutionModel
from quant_platform.execution.order_generator import OrderGenerator
from quant_platform.portfolio.equal_weight import EqualWeightPortfolio
from quant_platform.sample_data import generate_sample_market_data
from quant_platform.strategies.momentum import AShareMomentumStrategy, MomentumParameters
from quant_platform.universe.a_share import AShareUniverse, AShareUniverseConfig

SYMBOLS = ["000001.SZ", "000002.SZ", "600000.SH", "600036.SH"]
START = date(2023, 1, 3)
END = date(2023, 12, 29)
# 周三：不在周五调仓信号链路上，隔离除权估值本身的影响。
EX_DATE = date(2023, 6, 14)
PREV_TRADE_DATE = date(2023, 6, 13)


def _make_engine(repository) -> BacktestEngine:
    return BacktestEngine(
        repository=repository,
        universe=AShareUniverse(
            AShareUniverseConfig(
                tuple(SYMBOLS), minimum_history_days=61, minimum_average_amount=1.0
            )
        ),
        strategy=AShareMomentumStrategy("momentum", MomentumParameters(20, 60, 1.0)),
        portfolio=EqualWeightPortfolio(2),
        order_generator=OrderGenerator(100),
        execution_model=NextOpenExecutionModel(ExecutionConfig(slippage_rate=0.0)),
        rebalance="weekly",
    )


def _inject_ex_rights(tmp_path: Path, price_ratio: float, adjust_factors: bool = True):
    """在 EX_DATE 对全部股票注入除权事件。

    ``price_ratio`` 为除权日价格缩放比例（分红 0.9、送转 0.5）；
    ``adjust_factors=False`` 模拟没有复权因子的原始数据（因子恒 1），
    作为未复权估值的对照组。
    """

    repository = generate_sample_market_data(
        tmp_path / "market", SYMBOLS, date(2022, 1, 3), END
    )
    bars = repository.read_table("daily_bars")
    affected = pd.to_datetime(bars["trade_date"]) >= pd.Timestamp(EX_DATE)
    for column in (
        "raw_open",
        "raw_high",
        "raw_low",
        "raw_close",
        "pre_close",
        "up_limit",
        "down_limit",
    ):
        bars.loc[affected, column] *= price_ratio
    if adjust_factors:
        bars.loc[affected, "adj_factor"] /= price_ratio
    bars["adjusted_close"] = bars["raw_close"] * bars["adj_factor"]
    repository.save_table("daily_bars", bars)
    return repository


def _position_market_values(result, trade_date: date) -> dict[str, float]:
    positions = result.positions
    selected = positions[pd.to_datetime(positions["trade_date"]).dt.date == trade_date]
    return {str(row.symbol): float(row.market_value) for row in selected.itertuples()}


def _ex_date_daily_return(result) -> float:
    nav = result.nav
    selected = nav[pd.to_datetime(nav["trade_date"]).dt.date == EX_DATE]
    assert not selected.empty
    return float(selected["daily_return"].iloc[0])


def _assert_market_value_ratio(result, low: float, high: float) -> None:
    before = _position_market_values(result, PREV_TRADE_DATE)
    after = _position_market_values(result, EX_DATE)
    common = sorted(set(before) & set(after))
    assert common, "除权日前后应有持续持仓"
    for symbol in common:
        ratio = after[symbol] / before[symbol]
        assert low < ratio < high, f"{symbol} 市值比 {ratio}"


def test_cash_dividend_ex_date_keeps_nav_continuous(tmp_path: Path) -> None:
    repository = _inject_ex_rights(tmp_path, 0.9)
    result = _make_engine(repository).run(START, END, 1_000_000)

    # 10% 的现金分红除权：锚定估值下净值只体现正常日内波动。
    assert abs(_ex_date_daily_return(result)) < 0.03
    _assert_market_value_ratio(result, 0.97, 1.03)
    # 当日持仓因子已更新为 1/0.9，成本锚定仍为买入日因子 1。
    selected = result.positions[
        pd.to_datetime(result.positions["trade_date"]).dt.date == EX_DATE
    ]
    assert selected["cost_adj_factor"].tolist() == pytest.approx(
        [1.0] * len(selected)
    )
    assert selected["adj_factor"].astype(float).tolist() == pytest.approx(
        [1.0 / 0.9] * len(selected)
    )


def test_unadjusted_data_without_factors_shows_nav_jump(tmp_path: Path) -> None:
    repository = _inject_ex_rights(tmp_path, 0.9, adjust_factors=False)
    result = _make_engine(repository).run(START, END, 1_000_000)

    # 对照组：同样的价格跳低但无复权因子（因子恒 1），净值出现大幅跳变。
    assert _ex_date_daily_return(result) < -0.05
    _assert_market_value_ratio(result, 0.80, 0.97)


def test_share_split_ex_date_keeps_nav_continuous(tmp_path: Path) -> None:
    repository = _inject_ex_rights(tmp_path, 0.5)
    result = _make_engine(repository).run(START, END, 1_000_000)

    # 10送10：价格腰斩、因子翻倍，锚定估值下净值连续。
    assert abs(_ex_date_daily_return(result)) < 0.03
    _assert_market_value_ratio(result, 0.97, 1.03)
    positions = result.positions
    before = positions[pd.to_datetime(positions["trade_date"]).dt.date == PREV_TRADE_DATE]
    selected = positions[pd.to_datetime(positions["trade_date"]).dt.date == EX_DATE]
    common = sorted(set(before["symbol"]) & set(selected["symbol"]))
    assert common
    merged = before.set_index("symbol").loc[common, "quantity"].to_dict()
    for symbol, quantity in merged.items():
        row = selected.set_index("symbol").loc[symbol]
        # 持仓数量不变（以除权前股数为账面单位），因子翻倍补齐经济价值。
        assert int(row["quantity"]) == quantity
    assert selected["adj_factor"].astype(float).tolist() == pytest.approx(
        [2.0] * len(selected)
    )


def test_missing_adj_factor_falls_back_to_raw_with_warning(tmp_path: Path) -> None:
    repository = generate_sample_market_data(
        tmp_path / "market", SYMBOLS, date(2022, 1, 3), END
    )
    bars = repository.read_table("daily_bars").drop(columns=["adj_factor"])
    repository.save_table("daily_bars", bars)

    result = _make_engine(repository).run(START, END, 1_000_000)

    # 缺因子回退比率 1（未复权口径），回测仍可完成，但计入有效性告警。
    assert not result.nav.empty
    assert result.summary["missing_adj_factor_rows"] > 0
    issue = next(
        item for item in result.validity["issues"] if item["code"] == "MISSING_ADJ_FACTOR"
    )
    assert issue["severity"] == "WARNING"
    assert result.summary["validity_status"] == "WARNING"
    assert result.summary["metrics_reliable"] is True
