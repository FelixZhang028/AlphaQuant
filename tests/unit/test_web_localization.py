from __future__ import annotations

import pandas as pd

from quant_platform.web.localization import (
    localize_frame,
    localized_column_label,
    rebalance_label,
    status_label,
)


def test_localize_frame_translates_columns_and_enum_values() -> None:
    source = pd.DataFrame(
        {
            "symbol": ["000001.SZ"],
            "raw_open": [10.0],
            "side": ["BUY"],
            "status": ["FILLED"],
            "quality_status": ["OK"],
        }
    )

    result = localize_frame(source)

    assert list(result.columns) == [
        "股票代码",
        "未复权开盘价",
        "买卖方向",
        "状态",
        "数据质量状态",
    ]
    assert result.iloc[0]["买卖方向"] == "买入"
    assert result.iloc[0]["状态"] == "全部成交"
    assert result.iloc[0]["数据质量状态"] == "正常"


def test_common_interface_values_have_chinese_labels() -> None:
    assert rebalance_label("weekly") == "每周"
    assert status_label("ACTIVE") == "运行正常"


def test_localize_frame_handles_already_renamed_columns_and_general_values() -> None:
    source = pd.DataFrame(
        {
            "数据集": ["daily_bars"],
            "frequency": ["weekly"],
            "enabled": [True],
        }
    )

    result = localize_frame(source)

    assert result.iloc[0]["数据集"] == "股票日线行情"
    assert result.iloc[0]["frequency"] == "每周"
    assert result.iloc[0]["enabled"] == "是"


def test_research_result_headers_are_fully_localized() -> None:
    optimization_columns = [
        "optimization_id",
        "train_run_id",
        "objective_value",
        "risk_free_rate",
        "best_day_return",
        "max_drawdown_recovery_date",
        "order_fill_rate",
        "trade_win_rate",
        "profit_factor",
        "annualized_turnover",
        "average_concentration_hhi",
        "unknown_market_symbols",
    ]
    walk_forward_columns = [
        "test_run_id",
        "train_objective_value",
        "test_cumulative_return",
        "test_max_drawdown",
        "test_total_transaction_cost",
        "test_metrics_reliable",
        "test_unknown_status_orders",
    ]

    for column in optimization_columns + walk_forward_columns:
        label = localized_column_label(column)
        assert label != column
        assert "_" not in label
