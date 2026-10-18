"""Compare owned, persisted runs without inventing missing observations."""
import json
import math
import pandas as pd
from fastapi import HTTPException

from .result_adapter import _round
from .run_evidence import run_directory


def compare_persisted_runs(records):
    comparison, curves = [], {}
    for rid, row, result in records:
        directory = run_directory(result)
        if row["status"] != "完成" or directory is None:
            raise HTTPException(422, f"{rid} 没有可对比的已完成运行明细")
        try:
            nav = pd.read_parquet(directory / "nav.parquet")
            summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
            if not isinstance(summary, dict):
                raise ValueError("指标记录无效")
            dates = pd.to_datetime(nav["trade_date"], errors="coerce").dt.normalize()
            equity = pd.to_numeric(nav["equity"], errors="coerce")
            if dates.isna().any() or dates.duplicated().any() or equity.isna().any() or not equity.map(math.isfinite).all() or not equity.gt(0).all() or len(nav) < 2:
                raise ValueError("净值日期或数值无效")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(422, f"{rid} 运行明细缺失或损坏，无法对比") from exc
        curves[rid] = pd.Series(equity.to_numpy(), index=dates).sort_index()
        def percent(key, absolute=False):
            value = summary.get(key)
            return _round((abs(value) if absolute else value) * 100) if isinstance(value, (int, float)) else None
        comparison.append({
            "run_id": rid, "strategy": row["strategy"],
            "start_date": str(dates.min().date()), "end_date": str(dates.max().date()),
            "cumulative_return": percent("cumulative_return"), "annual_return": percent("annual_return"),
            "max_drawdown": percent("max_drawdown", True),
            **{k: _round(summary.get(k)) for k in ("sharpe", "sortino", "calmar")},
            **{k: result[k] for k in ("validity_status", "metrics_reliable", "legacy_unverified", "validity_issues")},
        })
    aligned = pd.concat(curves, axis=1, join="inner").sort_index()
    if len(aligned) < 2:
        raise HTTPException(422, "所选回测没有至少两个共同交易日，无法归一化对比")
    aligned = aligned.div(aligned.iloc[0]).round(8)
    aligned.index.name = "trade_date"
    points = aligned.reset_index()
    points["trade_date"] = points["trade_date"].dt.strftime("%Y-%m-%d")
    return {"comparison": comparison, "normalized_nav": points.to_dict(orient="records"),
            "source": "persisted_backtest", "metric_scope": "original_run",
            "chart_scope": {"start_date": points.trade_date.iloc[0], "end_date": points.trade_date.iloc[-1], "observations": len(points)},
            "note": "表格为各次回测原区间指标；曲线仅显示共同交易日，起点归一为 1，不填补缺失净值。"}
