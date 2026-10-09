"""Selection-bias evidence for one recorded parameter search.

Bailey & Lopez de Prado (2014), equations 2 and 9:
https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf
All Sharpe statistics in the formula use daily, non-annualized returns.
The correlation estimate is rounded up before the extreme-value approximation;
it is an estimate of trial dependence, not a correction for serial correlation.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import NormalDist
from typing import Any, cast

import numpy as np
import pandas as pd

DSR_CONFIDENCE = 0.95
MIN_OBSERVATIONS = 30
SCOPE_NOTE = (
    "仅覆盖本批实验记录，不含其他批次和人工尝试；独立试验数由收益相关性估计并向上取整。"
    "DSR 采用收益时点近似独立的假设，不能替代样本外验证，也不是未来盈利概率。"
)


@dataclass(frozen=True)
class SharpeSignificance:
    dsr: float
    psr: float
    benchmark: float


@dataclass(frozen=True)
class SelectionBiasResult:
    status: str
    message: str
    optimization_id: str | None = None
    objective: str | None = None
    trial_count: int | None = None
    valid_trials: int = 0
    effective_trials: int | None = None
    average_correlation: float | None = None
    best_median_gap: float | None = None
    dsr: float | None = None
    psr: float | None = None
    benchmark_sharpe: float | None = None
    observed_sharpe: float | None = None
    observations: int | None = None
    # Each row records inclusion and the reason for exclusions, including failures.
    evidence: tuple[dict[str, Any], ...] = ()


def unavailable_selection(message: str) -> SelectionBiasResult:
    return SelectionBiasResult("unavailable", message)


def unlinked_selection(run_kind: str) -> SelectionBiasResult:
    if run_kind == "walk_forward_oos":
        return SelectionBiasResult(
            "not_applicable", "该记录为滚动样本外测试；参数搜索校正应在对应训练期实验中查看。"
        )
    return unavailable_selection("未找到完整的参数搜索记录，无法核实尝试次数或评估选择偏差。")


def deflated_sharpe_ratio(
    *,
    sharpe: float,
    sharpe_variance: float,
    trials: int,
    observations: int,
    skewness: float,
    kurtosis: float,
) -> SharpeSignificance:
    """Return DSR and unadjusted PSR; kurtosis is Pearson (Normal == 3).

    N=1 has a zero selection benchmark and reduces to PSR. The caller must
    supply a complete, comparable trial family and non-annualized statistics.
    """
    if (
        not all(math.isfinite(x) for x in (sharpe, sharpe_variance, skewness, kurtosis))
        or sharpe_variance < 0
        or kurtosis < 1
        or trials < 1
        or int(trials) != trials
        or observations < 4
    ):
        raise ValueError("DSR 输入无效或收益观测不足。")
    normal = NormalDist()
    benchmark = 0.0
    if trials > 1:
        gamma = 0.5772156649015329
        benchmark = math.sqrt(sharpe_variance) * (
            (1 - gamma) * normal.inv_cdf(1 - 1 / trials)
            + gamma * normal.inv_cdf(1 - 1 / (trials * math.e))
        )
    variance = 1 - skewness * sharpe + (kurtosis - 1) * sharpe**2 / 4
    if not math.isfinite(variance) or variance <= 0:
        raise ValueError("收益高阶矩无法给出有效的 Sharpe 标准误。")
    scale = math.sqrt((observations - 1) / variance)
    return SharpeSignificance(
        dsr=normal.cdf((sharpe - benchmark) * scale),
        psr=normal.cdf(sharpe * scale),
        benchmark=benchmark,
    )


def _child(root: Path, identifier: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", identifier):
        raise ValueError("运行或实验编号无效。")
    path = (root / identifier).resolve()
    if path.parent != root.resolve():
        raise ValueError("运行或实验目录不在记录根目录下。")
    return path


def _mapping(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("实验记录格式无效。")
    return raw


def _returns(row: dict[str, Any], runs_root: Path) -> tuple[pd.Series, int, float]:
    if row.get("status") != "SUCCESS" or row.get("metrics_reliable") != True:  # noqa: E712
        raise ValueError("试验失败或绩效指标不可用。")
    annualization = float(row.get("annualization", float("nan")))
    risk_free = float(row.get("risk_free_rate", float("nan")))
    if (
        not math.isfinite(annualization)
        or annualization < 1
        or annualization != int(annualization)
        or not math.isfinite(risk_free)
        or risk_free <= -1
    ):
        raise ValueError("缺少有效的收益频率或无风险利率口径。")
    nav = pd.read_parquet(_child(runs_root, str(row.get("run_id", ""))) / "nav.parquet")
    if not {"trade_date", "equity"}.issubset(nav.columns):
        raise ValueError("净值缺少日期或权益字段。")
    dates = pd.to_datetime(nav["trade_date"], errors="coerce")
    equity = pd.to_numeric(nav["equity"], errors="coerce")
    if dates.isna().any() or dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError("净值日期缺失、重复或未按时间排序。")
    if not np.isfinite(equity.to_numpy(dtype=float)).all() or equity.le(0).any():
        raise ValueError("净值含缺失、非有限值或非正权益。")
    returns = pd.Series(equity.to_numpy(dtype=float), index=pd.DatetimeIndex(dates))
    returns = returns.pct_change(fill_method=None).iloc[1:]
    returns = returns - ((1 + risk_free) ** (1 / annualization) - 1)
    if len(returns) < MIN_OBSERVATIONS:
        raise ValueError(f"收益观测不足 {MIN_OBSERVATIONS} 个，无法稳定估计高阶矩。")
    volatility = float(returns.std())
    if (
        not np.isfinite(returns.to_numpy()).all()
        or not math.isfinite(volatility)
        or volatility <= 1e-12
    ):
        raise ValueError("收益无有效波动，无法计算 DSR。")
    sharpe = float(returns.mean() / returns.std()) * math.sqrt(annualization)
    stored_sharpe = float(row.get("sharpe", float("nan")))
    if not math.isclose(sharpe, stored_sharpe, rel_tol=1e-6, abs_tol=1e-8):
        raise ValueError("净值计算的 Sharpe 与已保存汇总不一致。")
    return returns, int(annualization), risk_free


def analyze_search(
    experiments: pd.DataFrame,
    runs_root: Path,
    *,
    optimization_id: str,
    objective: str,
    expected_trials: int,
) -> tuple[SelectionBiasResult, ...]:
    """Assess every row before eligibility filtering; do not hide failed trials.

    Incomplete families produce no probabilities: silently dropping missing or
    invalid trials would give a false impression of a complete correction.
    """
    records = [
        {str(key): value for key, value in row.items()} for row in experiments.to_dict("records")
    ]
    evidence: list[dict[str, Any]] = []
    samples: list[pd.Series | None] = []
    conventions: list[tuple[int, float]] = []
    for row in records:
        reason = "纳入计算（包含未满足排序约束的有效结果）。"
        returns = None
        try:
            returns, annualization, risk_free = _returns(row, runs_root)
            conventions.append((annualization, risk_free))
        except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) else "净值文件缺失或无法读取。"
        samples.append(returns)
        evidence.append(
            {
                "运行编号": str(row.get("run_id")) if pd.notna(row.get("run_id")) else "—",
                "试验状态": "成功" if row.get("status") == "SUCCESS" else "失败",
                "可计算": returns is not None,
                "年化 Sharpe": row.get("sharpe"),
                "说明": reason,
            }
        )
    usable = [sample for sample in samples if sample is not None]
    base = SelectionBiasResult(
        status="unavailable",
        message="",
        optimization_id=optimization_id,
        objective=objective,
        trial_count=expected_trials,
        valid_trials=len(usable),
        evidence=tuple(evidence),
    )

    def unavailable(message: str) -> tuple[SelectionBiasResult, ...]:
        return tuple(replace(base, message=message) for _ in records)

    ids = [str(row.get("run_id")) for row in records if pd.notna(row.get("run_id"))]
    if expected_trials < 1 or len(records) != expected_trials or len(ids) != len(set(ids)):
        return unavailable("试验清单数量不符或运行编号重复，无法核实完整搜索范围。")
    if expected_trials == 1:
        return (
            replace(
                base,
                status="not_applicable",
                effective_trials=1,
                message="本批只记录一次尝试，无需批内多重试验校正；不代表收益显著。",
            ),
        )
    if len(usable) != expected_trials:
        return unavailable(
            f"本批记录 {expected_trials} 次尝试，仅 {len(usable)} 次具备完整计算数据；"
            "存在失败、无效或缺失记录，无法完整评估选择偏差。"
        )
    if len(set(conventions)) != 1 or any(
        not sample.index.equals(usable[0].index) for sample in usable[1:]
    ):
        return unavailable("各试验的收益日期、频率或无风险利率不一致，无法比较。")
    if len(usable[0]) <= expected_trials:
        return unavailable("收益观测数不大于试验数，无法稳定估计试验间相关性。")
    matrix = pd.concat(usable, axis=1)
    matrix.columns = pd.RangeIndex(expected_trials)
    correlations = matrix.corr().to_numpy()
    rho = float(correlations[np.triu_indices(expected_trials, k=1)].mean())
    if not math.isfinite(rho):
        return unavailable("无法估计试验间的收益相关性。")
    rho_bounded = min(1.0, max(0.0, rho))
    effective = max(1, math.ceil(rho_bounded + (1 - rho_bounded) * expected_trials - 1e-10))
    sharpes = matrix.mean() / matrix.std(ddof=1)
    sharpe_values = sharpes.to_numpy(dtype=float)
    variance = float(sharpes.var(ddof=1))
    annualization = conventions[0][0]
    base = replace(
        base,
        effective_trials=effective,
        average_correlation=rho,
        observations=len(matrix),
        best_median_gap=float(sharpes.max() - sharpes.median()) * math.sqrt(annualization),
    )
    if variance <= 1e-20 and effective > 1:
        return unavailable("各试验 Sharpe 离散度为零，无法可靠估计选择门槛。")
    results: list[SelectionBiasResult] = []
    for index, sample in enumerate(usable):
        try:
            significance = deflated_sharpe_ratio(
                sharpe=float(sharpe_values[index]),
                sharpe_variance=variance,
                trials=effective,
                observations=len(sample),
                skewness=cast(float, sample.skew()),
                kurtosis=cast(float, sample.kurt()) + 3,
            )
        except ValueError as exc:
            results.append(replace(base, message=str(exc)))
            continue
        passed = significance.dsr >= DSR_CONFIDENCE
        message = (
            f"本结果来自 {expected_trials} 次尝试，估计独立试验 {effective} 次；"
            f"DSR 显著性 {significance.dsr:.1%}，"
            + (
                "达到 95% 参考门槛，仍需样本外验证。"
                if passed
                else "未达到 95% 参考门槛，请用未参与选参的数据验证。"
            )
        )
        if abs(float(sample.autocorr(lag=1))) > 1.96 / math.sqrt(len(sample)):
            passed = False
            message += "收益存在明显一阶自相关，未作时序相关修正，DSR 仅作近似参考。"
        results.append(
            replace(
                base,
                status="pass" if passed else "warn",
                message=message,
                dsr=significance.dsr,
                psr=significance.psr,
                benchmark_sharpe=significance.benchmark * math.sqrt(annualization),
                observed_sharpe=float(sharpe_values[index]) * math.sqrt(annualization),
            )
        )
    return tuple(results)


def load_search(
    directory: Path,
    runs_root: Path,
) -> tuple[pd.DataFrame, tuple[SelectionBiasResult, ...]]:
    request = _mapping(directory / "request.json")
    experiments = pd.read_csv(directory / "results.csv")
    count = request.get("combination_count")
    if not isinstance(count, int) or isinstance(count, bool):
        raise ValueError("实验未记录有效的尝试次数。")
    results = analyze_search(
        experiments,
        runs_root,
        optimization_id=directory.name,
        objective=str(request.get("objective", "未知")),
        expected_trials=count,
    )
    return experiments, results


def load_selection_bias(
    run_dir: Path,
    *,
    run_kind: str,
    parent_experiment_id: str | None,
) -> SelectionBiasResult:
    if run_kind == "walk_forward_oos":
        return unlinked_selection(run_kind)
    if not parent_experiment_id:
        return unlinked_selection(run_kind)
    try:
        directory = _child(run_dir.parent.parent / "optimizations", parent_experiment_id)
        frame, results = load_search(directory, run_dir.parent)
        selected = frame["run_id"].astype(str).eq(run_dir.name)
        positions = np.flatnonzero(selected.to_numpy())
        if len(positions) == 1:
            return results[int(positions[0])]
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        pass
    return replace(
        unavailable_selection("所属优化实验缺失、损坏或未唯一关联本结果，无法评估选择偏差。"),
        optimization_id=parent_experiment_id,
    )


def annotate_search(
    experiments: pd.DataFrame,
    results: tuple[SelectionBiasResult, ...],
) -> pd.DataFrame:
    """Keep original ordering and metrics; add probability and diagnostic columns."""
    frame = experiments.copy()
    frame["dsr"] = [result.dsr for result in results]
    labels = {"pass": "通过", "warn": "警告", "unavailable": "无法评估", "not_applicable": "不适用"}
    frame["selection_bias_status"] = [labels[result.status] for result in results]
    frame["selection_bias_reason"] = [result.message for result in results]
    return frame
