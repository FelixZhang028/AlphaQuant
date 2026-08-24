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

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class FactorPreprocessConfig:
    """可复用、可序列化的因子预处理配置。

    截面 z-score 是多因子合成的固定步骤，不作为可选项放在这里；本配置只
    描述合成前的去极值和缺失值处理，确保研究评估与回测执行使用同一口径。
    """

    winsorize: bool = False
    winsorize_method: str = "mad"
    fill_method: str = "drop"

    def __post_init__(self) -> None:
        if self.winsorize_method not in {"mad", "quantile"}:
            raise ValueError(f"未知去极值方法: {self.winsorize_method}")
        if self.fill_method not in {"drop", "median"}:
            raise ValueError(f"未知缺失值处理方法: {self.fill_method}")

    def to_dict(self) -> dict[str, object]:
        return {
            "winsorize": self.winsorize,
            "winsorize_method": self.winsorize_method,
            "fill_method": self.fill_method,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> FactorPreprocessConfig:
        if data is None:
            return cls()
        enabled = data.get("winsorize", False)
        if not isinstance(enabled, bool):
            raise ValueError("winsorize 必须是布尔值")
        return cls(
            winsorize=enabled,
            winsorize_method=str(data.get("winsorize_method", "mad")),
            fill_method=str(data.get("fill_method", "drop")),
        )


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
        mad = (value - median).abs().groupby(result["date"], observed=True).transform("median")
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


def preprocess_factor(
    frame: pd.DataFrame,
    config: FactorPreprocessConfig | None = None,
) -> pd.DataFrame:
    """按配置清洗单个因子长表，供研究和策略执行共同调用。"""

    resolved = config or FactorPreprocessConfig()
    result = frame.copy()
    if resolved.winsorize:
        result = winsorize(result, method=resolved.winsorize_method)
    return fill_missing(result, method=resolved.fill_method)


def preprocess_factor_frames(
    frames: Mapping[str, pd.DataFrame],
    config: FactorPreprocessConfig | None = None,
) -> dict[str, pd.DataFrame]:
    """先按全部成分的日期/股票并集对齐，再用同一配置逐因子清洗。

    对齐是“中位数填充”真正生效的前提：某只股票缺少某个因子值时，长表中
    原本没有这一行，必须先补成缺失值才能进行横截面填充。
    """

    if not frames:
        return {}
    keys = pd.concat(
        [frame[["date", "symbol"]] for frame in frames.values()],
        ignore_index=True,
    ).drop_duplicates()
    keys["date"] = pd.to_datetime(keys["date"]).dt.normalize()
    result: dict[str, pd.DataFrame] = {}
    for name, frame in frames.items():
        values = frame[["date", "symbol", "value"]].copy()
        values["date"] = pd.to_datetime(values["date"]).dt.normalize()
        values = values.drop_duplicates(["date", "symbol"], keep="last")
        aligned = keys.merge(values, on=["date", "symbol"], how="left")
        result[name] = preprocess_factor(aligned, config)
    return result


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
    industry_mean = value.groupby([result["date"], result["industry"]], observed=True).transform(
        "mean"
    )
    result["value"] = value - industry_mean
    return result[["date", "symbol", "value"]].reset_index(drop=True)
