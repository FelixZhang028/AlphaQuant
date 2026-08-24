"""因子评估：IC / 分层收益 / 换手率 / 样本外稳定性。

因果性约定（防未来函数）：

- 因子值只用 ``<= end_date`` 的行情计算（评估区间内 t 日因子天然只依赖
  t 日及之前的数据，见 ``base.FactorDefinition`` 约定）；
- 未来收益严格定义为 t+1 日收盘买入、持有 N 个交易日后在 t+N+1
  日收盘卖出：``fwd_ret(t) = close(t+N+1) / close(t+1) - 1``；
- IC 与分层统计均使用「因子值 × direction」后的调整值，
  因此正的 IC / 正的多空收益代表因子按预期方向有效。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository
from quant_platform.factors.base import FactorDefinition, pivot_field
from quant_platform.factors.preprocess import (
    FactorPreprocessConfig,
    preprocess_factor,
)


def chronological_train_test_split(
    dates: Iterable[object], *, train_ratio: float = 0.7
) -> tuple[date, date]:
    """按交易日顺序切分训练期结束日和测试期开始日。"""

    if not 0.0 < train_ratio < 1.0:
        raise ValueError("train_ratio 必须在 0 和 1 之间")
    ordered = pd.DatetimeIndex(pd.to_datetime(list(dates), errors="coerce"))
    ordered = ordered.dropna().normalize().unique().sort_values()
    if len(ordered) < 2:
        raise ValueError("至少需要两个有效交易日才能划分训练期和测试期")
    split_index = min(max(int(len(ordered) * train_ratio), 1), len(ordered) - 1)
    return ordered[split_index - 1].date(), ordered[split_index].date()


@dataclass(frozen=True)
class FactorReport:
    """单因子评估报告，全部为 DataFrame / 标量，便于网页直接展示。"""

    factor_name: str
    display_name: str
    horizon: int
    n_groups: int
    daily_ic: pd.DataFrame  # date / ic / rank_ic
    ic_mean: float
    ic_ir: float
    rank_ic_mean: float
    rank_ic_ir: float
    group_returns: pd.DataFrame  # date / group / ret
    group_mean_returns: pd.Series  # group -> 平均未来收益
    long_short_mean: float  # 顶组 - 底组 平均收益
    turnover: pd.DataFrame  # date / turnover（相邻期 top 组换手）
    turnover_mean: float
    first_half_ic: float  # 样本前半段 Rank IC 均值
    second_half_ic: float  # 样本后半段 Rank IC 均值
    notes: list[str] = field(default_factory=list)


class FactorEvaluator:
    """基于本地行情仓库的因子评估器。"""

    def __init__(self, repository: ParquetMarketDataRepository) -> None:
        self.repository = repository

    def evaluate(
        self,
        factor: FactorDefinition,
        start_date: date,
        end_date: date,
        *,
        symbols: list[str] | None = None,
        horizon: int = 5,
        n_groups: int = 5,
        preprocess: FactorPreprocessConfig | None = None,
    ) -> FactorReport:
        """评估因子在 [start_date, end_date] 的横截面选股能力。"""

        if horizon < 1:
            raise ValueError("horizon 必须 >= 1")
        if n_groups < 2:
            raise ValueError("n_groups 必须 >= 2")

        # 因子值严格只用 <= end_date 的行情；未来收益另取全量价格。
        factor_bars = self.repository.get_daily_bars(symbols=symbols, end_date=end_date)
        if factor_bars.empty:
            raise ValueError("评估区间内没有行情数据")
        values = factor.compute(factor_bars)
        if preprocess is not None:
            sample_keys = factor_bars[["trade_date", "symbol"]].rename(
                columns={"trade_date": "date"}
            )
            sample_keys["date"] = pd.to_datetime(sample_keys["date"]).dt.normalize()
            values["date"] = pd.to_datetime(values["date"]).dt.normalize()
            values = sample_keys.drop_duplicates().merge(
                values[["date", "symbol", "value"]],
                on=["date", "symbol"],
                how="left",
            )
            values = preprocess_factor(values, preprocess)
        values["date"] = pd.to_datetime(values["date"]).dt.normalize()
        values = values[
            values["date"].between(pd.Timestamp(start_date), pd.Timestamp(end_date))
        ].copy()
        values["adjusted"] = pd.to_numeric(values["value"], errors="coerce") * factor.direction

        returns = self._forward_returns(symbols, horizon)
        merged = values.merge(returns, on=["date", "symbol"], how="inner")
        merged = merged.dropna(subset=["adjusted", "fwd_ret"])

        daily_ic = self._daily_ic(merged)
        group_returns, group_means, long_short = self._group_returns(merged, n_groups)
        turnover = self._top_turnover(merged, n_groups)

        rank_ic = daily_ic["rank_ic"].dropna()
        half = len(rank_ic) // 2
        first_half = float(rank_ic.iloc[:half].mean()) if half else float("nan")
        second_half = float(rank_ic.iloc[half:].mean()) if len(rank_ic) > half else float("nan")

        notes: list[str] = []
        if len(daily_ic) < 20:
            notes.append("有效截面不足 20 日，统计结论仅供参考")

        ic = daily_ic["ic"].dropna()
        return FactorReport(
            factor_name=factor.name,
            display_name=factor.display_name,
            horizon=horizon,
            n_groups=n_groups,
            daily_ic=daily_ic,
            ic_mean=float(ic.mean()) if len(ic) else float("nan"),
            ic_ir=self._ir(ic),
            rank_ic_mean=float(rank_ic.mean()) if len(rank_ic) else float("nan"),
            rank_ic_ir=self._ir(rank_ic),
            group_returns=group_returns,
            group_mean_returns=group_means,
            long_short_mean=long_short,
            turnover=turnover,
            turnover_mean=(
                float(turnover["turnover"].mean()) if not turnover.empty else float("nan")
            ),
            first_half_ic=first_half,
            second_half_ic=second_half,
            notes=notes,
        )

    def _forward_returns(self, symbols: list[str] | None, horizon: int) -> pd.DataFrame:
        """t+1 收盘买入、持有 horizon 日后收盘卖出的未来收益（date=t）。"""

        bars = self.repository.get_daily_bars(symbols=symbols)
        price_field = (
            "adjusted_close"
            if "adjusted_close" in bars.columns and bars["adjusted_close"].notna().any()
            else "raw_close"
        )
        close = pivot_field(bars, price_field)
        entry = close.shift(-1)
        exit_ = close.shift(-(horizon + 1))
        fwd = exit_ / entry - 1.0
        long = fwd.stack(future_stack=True).rename("fwd_ret").reset_index()
        long.columns = pd.Index(["date", "symbol", "fwd_ret"])
        return long.dropna(subset=["fwd_ret"])

    @staticmethod
    def _daily_ic(merged: pd.DataFrame) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        for trade_date, group in merged.groupby("date", observed=True):
            if len(group) < 3:
                continue
            ic = group["adjusted"].corr(group["fwd_ret"], method="pearson")
            rank_ic = group["adjusted"].corr(group["fwd_ret"], method="spearman")
            rows.append({"date": trade_date, "ic": ic, "rank_ic": rank_ic})
        return pd.DataFrame(rows, columns=["date", "ic", "rank_ic"])

    @staticmethod
    def _group_returns(
        merged: pd.DataFrame, n_groups: int
    ) -> tuple[pd.DataFrame, pd.Series, float]:
        rows: list[dict[str, object]] = []
        for trade_date, group in merged.groupby("date", observed=True):
            if len(group) < n_groups:
                continue
            labels = pd.qcut(group["adjusted"], n_groups, labels=False, duplicates="drop")
            for label, bucket in group.groupby(labels, observed=True):
                rows.append(
                    {
                        "date": trade_date,
                        "group": int(label) + 1,
                        "ret": float(bucket["fwd_ret"].mean()),
                    }
                )
        frame = pd.DataFrame(rows, columns=["date", "group", "ret"])
        if frame.empty:
            return frame, pd.Series(dtype=float), float("nan")
        means = frame.groupby("group", observed=True)["ret"].mean()
        long_short = float(means.iloc[-1] - means.iloc[0])
        return frame, means, long_short

    @staticmethod
    def _top_turnover(merged: pd.DataFrame, n_groups: int) -> pd.DataFrame:
        """相邻两个交易日 top 组的换手率：1 - 重合度。"""

        top_sets: list[tuple[pd.Timestamp, set[str]]] = []
        for trade_date, group in merged.groupby("date", observed=True):
            if len(group) < n_groups:
                continue
            labels = pd.qcut(group["adjusted"], n_groups, labels=False, duplicates="drop")
            top_label = labels.max()
            top_sets.append((trade_date, set(group.loc[labels == top_label, "symbol"])))
        rows: list[dict[str, object]] = []
        for (_, prev), (trade_date, current) in zip(top_sets, top_sets[1:], strict=False):
            overlap = len(prev & current) / len(current) if current else 0.0
            rows.append({"date": trade_date, "turnover": 1.0 - overlap})
        return pd.DataFrame(rows, columns=["date", "turnover"])

    @staticmethod
    def _ir(series: pd.Series) -> float:
        std = float(series.std())
        if not len(series) or std == 0.0 or pd.isna(std):
            return float("nan")
        return float(series.mean()) / std
