"""因子清洗预处理：去极值、标准化、缺失值处理、行业中性化。

所有操作均按交易日（date）在横截面上进行，输入输出都是因子标准长表
``(date, symbol, value)``。实现统一使用 ``groupby(...).transform``，
保证行序、索引与 ``date`` 列原样保留。

行业中性化说明：当前 ``security_master`` 表只有
symbol/name/exchange/list_status/list_date/delist_date 等字段，
**没有行业分类字段**，因此 ``neutralize_industry`` 需要调用方显式提供
行业映射；未提供时原样返回（即跳过中性化），不静默做伪中性化。
"""

from __future__ import annotations

import pandas as pd


def winsorize(
    frame: pd.DataFrame,
    *,
    method: str = "mad",
    n_mad: float = 5.0,
    quantile: float = 0.01,
) -> pd.DataFrame:
    """按日横截面去极值。

    - ``method="mad"``：中位数 ± n_mad × 1.4826 × MAD 截断；
    - ``method="quantile"``：按 [quantile, 1-quantile] 分位数截断。
    """

    result = frame.copy()
    value = pd.to_numeric(result["value"], errors="coerce")
    grouped = value.groupby(result["date"], observed=True)
    if method == "mad":
        median = grouped.transform("median")
        mad = (value - median).abs().groupby(result["date"], observed=True).transform(
            "median"
        )
        lower = median - n_mad * 1.4826 * mad
        upper = median + n_mad * 1.4826 * mad
    elif method == "quantile":
        lower = grouped.transform(lambda series: series.quantile(quantile))
        upper = grouped.transform(lambda series: series.quantile(1.0 - quantile))
    else:
        raise ValueError(f"未知去极值方法: {method}")
    result["value"] = value.clip(lower, upper)
    return result.reset_index(drop=True)


def zscore(frame: pd.DataFrame) -> pd.DataFrame:
    """按日横截面 z-score 标准化；截面标准差为 0 时输出 0。"""

    result = frame.copy()
    value = pd.to_numeric(result["value"], errors="coerce")
    grouped = value.groupby(result["date"], observed=True)
    mean = grouped.transform("mean")
    std = grouped.transform("std").fillna(0.0)
    normalized = (value - mean) / std.where(std > 0.0, other=1.0)
    result["value"] = normalized.where(std > 0.0, other=0.0)
    return result.reset_index(drop=True)


def fill_missing(frame: pd.DataFrame, *, method: str = "median") -> pd.DataFrame:
    """缺失值处理。

    - ``method="median"``：按日横截面中位数填充；
    - ``method="drop"``：剔除当日有缺失的样本。
    """

    if method == "drop":
        return frame.dropna(subset=["value"]).reset_index(drop=True)
    if method != "median":
        raise ValueError(f"未知缺失值处理方法: {method}")
    result = frame.copy()
    value = pd.to_numeric(result["value"], errors="coerce")
    median = value.groupby(result["date"], observed=True).transform("median")
    result["value"] = value.fillna(median)
    return result.reset_index(drop=True)


def neutralize_industry(
    frame: pd.DataFrame,
    industry_map: dict[str, str] | None = None,
) -> pd.DataFrame:
    """行业中性化：按日、按行业对因子值去均值。

    ``security_master`` 当前不含行业字段，因此必须显式传入
    ``industry_map``（symbol -> 行业名称）。未提供时原样返回并视为跳过。
    """

    if not industry_map:
        return frame.reset_index(drop=True)

    result = frame.copy()
    result["industry"] = result["symbol"].map(industry_map)
    value = pd.to_numeric(result["value"], errors="coerce")
    industry_mean = value.groupby(
        [result["date"], result["industry"]], observed=True
    ).transform("mean")
    result["value"] = value - industry_mean
    return result[["date", "symbol", "value"]].reset_index(drop=True)
