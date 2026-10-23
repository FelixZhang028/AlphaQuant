"""Which stocks meet a rule strategy's conditions on one day (normally the newest local trading day).

It uses the same condition and ranking code as the backtest (``rule_based.rank_score``), so a stock
is listed here exactly when the strategy would consider it on that day. The list only describes the
data: the conditions are the user's own, nothing here is a recommendation.
"""

from __future__ import annotations

from datetime import date
from math import isfinite
from typing import Any

import pandas as pd

from quant_platform.strategies.rule_based import indicator_value, rank_score
from quant_platform.strategies.rule_schema import RuleStrategyDefinition

_NUMERIC = ("adjusted_close", "amount", "raw_close", "pre_close")


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def screen(definition: RuleStrategyDefinition, bars: pd.DataFrame, day: date, *,
           exclude_st: bool = True, exclude_suspended: bool = True) -> dict[str, Any]:
    """``{checked, matched, items}``: the stocks with a bar on ``day`` that pass, best first.

    ``bars`` holds each stock's history up to ``day`` (``adjusted_close`` and ``amount`` at least).
    Stocks without a bar that day, ST stocks and suspended stocks are left out (the last two on request).
    Each item has the latest price, the day's change, the ranking value and the values behind every condition.
    """

    if bars.empty:
        return {"checked": 0, "matched": 0, "items": []}
    frame = bars.copy()
    for column in _NUMERIC:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    cutoff = pd.Timestamp(day)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    # 排序、按日期截断、找出每只股票的最后一天都只做一次，不在每只股票里各做一遍
    frame = frame[frame["trade_date"] <= cutoff].sort_values(["symbol", "trade_date"], kind="stable")
    last_rows = frame.groupby("symbol", observed=True, sort=False).tail(1).set_index("symbol")
    keep = last_rows["trade_date"] == cutoff
    if exclude_st and "is_st" in last_rows.columns:
        keep &= ~last_rows["is_st"].fillna(False).astype(bool)
    if exclude_suspended and "is_suspended" in last_rows.columns:
        keep &= ~last_rows["is_suspended"].fillna(False).astype(bool)
    wanted = set(last_rows.index[keep])
    frame = frame[frame["symbol"].isin(wanted)]
    checked = len(wanted)
    items: list[dict[str, Any]] = []
    for symbol, group in frame.groupby("symbol", observed=True, sort=False):
        score = rank_score(group, definition)
        if score is None:
            continue
        last = group.iloc[-1]
        close, previous = _number(last.get("raw_close")), _number(last.get("pre_close"))
        items.append({
            "symbol": str(symbol),
            "close": close,
            "change": close / previous - 1.0 if close is not None and previous else None,
            "score": score,
            "ranking": indicator_value(group, definition.ranking.indicator),
            "conditions": [
                {"left": indicator_value(group, rule.left),
                 "right": indicator_value(group, rule.right) if rule.right is not None else rule.value}
                for rule in definition.entry_rules
            ],
        })
    items.sort(key=lambda item: (-item["score"], item["symbol"]))
    for item in items:
        item.pop("score")
    return {"checked": checked, "matched": len(items), "items": items}
