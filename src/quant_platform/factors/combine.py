"""多因子合成：加权组合、横截面相关性分析与高相关剔除。

输入输出均为因子标准长表 ``(date, symbol, value)``。合成前每个因子先按日
横截面 z-score 标准化（乘以各自 ``direction`` 使“值越大越看好”），再按权重
加权求和；权重无需归一化，合成时自动按权重绝对值之和归一。

因果性约定：所有操作只在同一 ``date`` 的横截面上进行，不跨日期引用数据，
因此合成因子与成分因子一样满足防未来函数要求。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from quant_platform.factors.base import FACTOR_COLUMNS, FactorDefinition
from quant_platform.factors.preprocess import zscore


def combine_factors(
    frames: dict[str, pd.DataFrame],
    weights: dict[str, float],
    *,
    directions: dict[str, int] | None = None,
) -> pd.DataFrame:
    """把多个因子长表合成为一个因子长表。

    - ``frames``：因子名 -> 因子标准长表；
    - ``weights``：因子名 -> 权重（自动归一化，允许 0）；
    - ``directions``：因子名 -> 方向（1 或 -1），缺省视为 1。
    """

    if not frames:
        raise ValueError("至少需要一个因子")
    unknown = sorted(set(weights).difference(frames))
    if unknown:
        raise ValueError(f"权重包含未提供的因子: {unknown}")
    total = sum(abs(float(weights.get(name, 0.0))) for name in frames)
    if total <= 0:
        raise ValueError("权重之和不能为 0")

    merged: pd.DataFrame | None = None
    for name, frame in frames.items():
        weight = float(weights.get(name, 0.0)) / total
        direction = (directions or {}).get(name, 1)
        if direction not in (1, -1):
            raise ValueError(f"因子 {name} 的 direction 只能是 1 或 -1")
        adjusted = frame.copy()
        adjusted["value"] = pd.to_numeric(adjusted["value"], errors="coerce") * direction
        normalized = zscore(adjusted.dropna(subset=["value"]))
        normalized = normalized.rename(columns={"value": name})[
            ["date", "symbol", name]
        ]
        normalized[name] = normalized[name] * weight
        merged = (
            normalized
            if merged is None
            else merged.merge(normalized, on=["date", "symbol"], how="outer")
        )

    assert merged is not None
    value_cols = [name for name in frames]
    # 外连接后缺失视为 0（该因子当日无观点），权重已在各列内部归一。
    merged["value"] = merged[value_cols].fillna(0.0).sum(axis=1)
    result = merged[["date", "symbol", "value"]].copy()
    result["date"] = pd.to_datetime(result["date"]).dt.normalize()
    return result.sort_values(["date", "symbol"]).reset_index(drop=True)[FACTOR_COLUMNS]


def correlation_matrix(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """因子间相关性矩阵：按日横截面 Spearman 相关，再对各日取均值。

    返回 index/columns 均为因子名的方阵；因子不足两个时返回空表。
    """

    if len(frames) < 2:
        return pd.DataFrame()
    series: dict[str, pd.Series] = {}
    for name, frame in frames.items():
        adjusted = frame.copy()
        adjusted["value"] = pd.to_numeric(adjusted["value"], errors="coerce")
        series[name] = adjusted.set_index(["date", "symbol"])["value"]
    panel = pd.DataFrame(series).dropna(how="any")
    if panel.empty:
        return pd.DataFrame()
    dates = panel.index.get_level_values("date")
    daily_corrs = [
        panel.loc[dates == trade_date].corr(method="spearman")
        for trade_date in dates.unique()
        if len(panel.loc[dates == trade_date]) >= 3
    ]
    if not daily_corrs:
        return pd.DataFrame()
    stacked = pd.concat(daily_corrs)
    return stacked.groupby(level=0, observed=True).mean().reindex(columns=panel.columns)


def drop_highly_correlated(
    corr: pd.DataFrame,
    *,
    threshold: float = 0.7,
    priority: list[str] | None = None,
) -> list[str]:
    """贪心剔除高相关因子，返回被剔除的因子名列表。

    ``priority`` 给出保留偏好（越靠前越优先保留），缺省按矩阵顺序。
    每对 |corr| >= threshold 的因子中剔除优先级靠后的一个。
    """

    if corr.empty or len(corr) < 2:
        return []
    order = [name for name in (priority or []) if name in corr.columns]
    order += [name for name in corr.columns if name not in order]
    kept: list[str] = []
    dropped: list[str] = []
    for name in order:
        if any(
            abs(float(corr.loc[name, other])) >= threshold for other in kept
        ):
            dropped.append(name)
        else:
            kept.append(name)
    return dropped


@dataclass(frozen=True)
class CompositeFactor(FactorDefinition):
    """由成分因子加权合成的复合因子，可直接交给 FactorEvaluator 评估。"""

    components: tuple[FactorDefinition, ...] = field(default_factory=tuple)
    weights: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.components:
            raise ValueError("复合因子至少需要一个成分因子")
        names = [item.name for item in self.components]
        if len(set(names)) != len(names):
            raise ValueError("成分因子名称重复")
        unknown = sorted(set(self.weights).difference(names))
        if unknown:
            raise ValueError(f"权重包含未知成分因子: {unknown}")
        object.__setattr__(
            self, "min_history", max(item.min_history for item in self.components)
        )
        required: list[str] = []
        for item in self.components:
            for field_name in item.required_fields:
                if field_name not in required:
                    required.append(field_name)
        object.__setattr__(self, "required_fields", tuple(required))

    def compute(self, bars: pd.DataFrame) -> pd.DataFrame:
        frames = {item.name: item.compute(bars) for item in self.components}
        directions = {item.name: item.direction for item in self.components}
        weights = {name: float(self.weights.get(name, 1.0)) for name in frames}
        return combine_factors(frames, weights, directions=directions)
