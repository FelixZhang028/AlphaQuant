from __future__ import annotations

import pandas as pd

from quant_platform.web.localization import localize_frame, rebalance_label, status_label


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
