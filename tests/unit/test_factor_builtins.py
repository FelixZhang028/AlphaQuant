"""内置因子价格口径测试。"""

from __future__ import annotations

import pandas as pd
import pytest

from quant_platform.factors.builtins import builtin_factors


def test_high_distance_uses_raw_close_and_raw_high_consistently() -> None:
    bars = pd.DataFrame(
        {
            "trade_date": pd.date_range("2024-01-01", periods=20),
            "symbol": ["AAA"] * 20,
            "raw_close": [9.0] * 20,
            "raw_high": [10.0] * 20,
            # 故意使用完全不同的复权尺度，确保计算不再混用该列。
            "adjusted_close": [90.0] * 20,
        }
    )
    factor = next(item for item in builtin_factors() if item.name == "high_distance_20")

    result = factor.compute(bars)

    assert factor.required_fields == ("raw_close", "raw_high")
    assert result.iloc[-1]["value"] == pytest.approx(9.0 / 10.0 - 1.0)
