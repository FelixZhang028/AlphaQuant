"""Fit factor combinations on training data and compare frozen models on a holdout."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from math import isfinite

import pandas as pd

from quant_platform.factors.base import FactorDefinition
from quant_platform.factors.combine import combine_factors, correlation_matrix, prepare_frames
from quant_platform.factors.evaluation import FactorEvaluator, FactorReport


@dataclass(frozen=True)
class FrameFactor(FactorDefinition):
    values: pd.DataFrame = field(default_factory=pd.DataFrame)

    def compute(self, bars: pd.DataFrame) -> pd.DataFrame:
        cutoff = pd.to_datetime(bars["trade_date"]).max()
        return self.values[self.values.date <= cutoff].copy()


class BoundedRepository:
    """Cap both factor history and forward-return prices at the phase boundary."""

    def __init__(self, repository, end: date):
        self.repository, self.end = repository, end

    def get_daily_bars(self, symbols=None, end_date=None):
        cutoff = min(pd.Timestamp(end_date or self.end), pd.Timestamp(self.end)).date()
        return self.repository.get_daily_bars(symbols=symbols, end_date=cutoff)


@dataclass
class CombinationResult:
    weights: dict[str, float]
    correlation: pd.DataFrame
    comparison: pd.DataFrame
    reports: dict[str, FactorReport]
    spec: list[dict]


def research_combination(
    repository,
    components: tuple[FactorDefinition, ...],
    *,
    train_start: date,
    train_end: date,
    test_start: date,
    test_end: date,
    mode: str = "equal",
    custom_weights: dict[str, float] | None = None,
    clip: bool = True,
    missing: str = "drop",
    horizon: int = 5,
    n_groups: int = 5,
) -> CombinationResult:
    if not train_start <= train_end < test_start <= test_end:
        raise ValueError("日期需满足：训练开始 ≤ 训练结束 < 测试开始 ≤ 测试结束。")
    if len(components) < 2 or len({f.name for f in components}) != len(components):
        raise ValueError("请选择至少两个不同因子。")
    if mode not in {"equal", "manual", "ic"}:
        raise ValueError("未知权重方式")
    if missing not in {"drop", "median"}:
        raise ValueError("研究组合请选择剔除缺失或中位数填充。")

    def frames_until(end):
        bars = repository.get_daily_bars(end_date=end)
        if bars.empty:
            raise ValueError("所选区间没有本地行情，请先更新数据。")
        universe = bars[["trade_date", "symbol"]].rename(columns={"trade_date": "date"})
        universe["date"] = pd.to_datetime(universe["date"]).dt.normalize()
        frames = {}
        for factor in components:
            values = factor.compute(bars)
            values["date"] = pd.to_datetime(values["date"]).dt.normalize()
            frames[factor.name] = universe.merge(values, on=["date", "symbol"], how="left")
        return prepare_frames(frames, clip=clip, missing=missing)

    train_frames = frames_until(train_end)
    train_slice = {
        name: frame[frame.date.between(pd.Timestamp(train_start), pd.Timestamp(train_end))]
        for name, frame in train_frames.items()
    }
    if any(frame.empty for frame in train_slice.values()):
        raise ValueError("训练期清洗后没有共同样本，请扩大日期范围或补齐行情。")
    correlation = correlation_matrix(train_slice)
    weights = {}
    for factor in components:
        if mode == "equal":
            weight = 1.0
        elif mode == "manual":
            weight = float((custom_weights or {}).get(factor.name, 0))
        else:
            proxy = FrameFactor(
                name=factor.name,
                display_name=factor.display_name,
                direction=factor.direction,
                values=train_frames[factor.name],
            )
            report = FactorEvaluator(BoundedRepository(repository, train_end)).evaluate(
                proxy, train_start, train_end, horizon=horizon, n_groups=n_groups
            )
            weight = report.rank_ic_mean
            weight = max(weight, 0.0) if isfinite(weight) else 0.0
        if not isfinite(weight) or weight < 0:
            raise ValueError("权重必须是非负有限数值；因子方向由因子定义统一处理。")
        weights[factor.name] = weight
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("没有正权重：请调整手动权重，或改用等权；训练期负 IC 不会自动取绝对值。")
    weights = {name: value / total for name, value in weights.items()}

    # The test set is accessed only after all weights are fixed.
    frames = frames_until(test_end)
    directions = {factor.name: factor.direction for factor in components}
    candidates = {
        f"单因子 · {factor.display_name} ({factor.name})": FrameFactor(
            name=factor.name,
            display_name=factor.display_name,
            direction=factor.direction,
            values=frames[factor.name],
        )
        for factor in components
    }
    for label, model_weights in [
        ("等权组合", {f.name: 1.0 for f in components}),
        ("我的组合", weights),
    ]:
        candidates[label] = FrameFactor(
            name=label,
            display_name=label,
            values=combine_factors(frames, model_weights, directions=directions, missing="drop"),
        )
    reports = {}
    rows = []
    evaluator = FactorEvaluator(BoundedRepository(repository, test_end))
    for label, factor in candidates.items():
        report = evaluator.evaluate(
            factor, test_start, test_end, horizon=horizon, n_groups=n_groups
        )
        reports[label] = report
        rows.append(
            {
                "方案": label,
                "Rank IC": report.rank_ic_mean,
                "Rank IC IR": report.rank_ic_ir,
                "IC": report.ic_mean,
                "同日多空收益差": report.long_short_mean,
                "成员更替率": report.turnover_mean,
                "有效 IC 天数": int(report.daily_ic.rank_ic.notna().sum()),
            }
        )
    if not any(row["有效 IC 天数"] for row in rows):
        raise ValueError("测试期没有有效 IC 样本，请检查日期、股票数量和因子是否为常数。")
    spec = [
        {"name": f.name, "weight": weights[f.name], "clip": clip, "missing": missing}
        for f in components
    ]
    return CombinationResult(weights, correlation, pd.DataFrame(rows), reports, spec)
