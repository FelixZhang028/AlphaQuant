"""Checks on stored index bars (``benchmark_bars``), so a wrong download cannot sit there unnoticed.

An index never moves 20% in a day, and its level never halves or doubles within a few weeks. Bars
that break these rules come from a mix-up, for example a stock with the same six digits as the
index (sh.000001 is the Shanghai Composite, sz.000001 is Ping An Bank). ``jumps`` finds them in a
download before it is saved; ``outliers`` finds them in what is already stored, so they can be
removed and downloaded again.
"""

from __future__ import annotations

import pandas as pd

# 指数一天涨跌超过这个比例，就不可能是真的。
MAX_INDEX_MOVE = 0.20
# 和前后几周的中位数差一倍以上，就不可能是真的指数点位。
OUTLIER_FACTOR = 2.0
OUTLIER_CONTEXT = 60          # 和前后各这么多个交易日比


def fill_first_pre_close(new: pd.DataFrame, existing: pd.DataFrame) -> pd.DataFrame:
    """A download's first bar has no previous close of its own; take the stored bar before it."""

    if new.empty or existing.empty:
        return new
    new = new.sort_values(["symbol", "trade_date"]).copy()
    stored = existing.copy()
    stored["trade_date"] = pd.to_datetime(stored["trade_date"]).dt.normalize()
    for symbol, rows in new.groupby("symbol"):
        first = rows.index[0]
        if pd.notna(new.at[first, "pre_close"]):
            continue
        before = stored[(stored["symbol"] == symbol) & (stored["trade_date"] < new.at[first, "trade_date"])]
        if not before.empty:
            new.at[first, "pre_close"] = float(before.sort_values("trade_date")["raw_close"].iloc[-1])
    return new


def jumps(frame: pd.DataFrame, limit: float = MAX_INDEX_MOVE) -> pd.DataFrame:
    """Bars whose close is more than ``limit`` away from their previous close."""

    if frame.empty:
        return frame
    close = pd.to_numeric(frame["raw_close"], errors="coerce")
    pre = pd.to_numeric(frame["pre_close"], errors="coerce")
    move = (close / pre - 1).where(pre > 0)
    return frame[move.abs() > limit]


def outliers(frame: pd.DataFrame, factor: float = OUTLIER_FACTOR, context: int = OUTLIER_CONTEXT) -> pd.DataFrame:
    """Stored bars at a level that cannot be the index.

    The series is cut wherever the close moves more than :data:`MAX_INDEX_MOVE` from the bar
    before. Each piece then takes a vote among the bars from ``context`` before it to ``context``
    after it (itself included): bars within ``factor`` of the piece's median agree with it, the
    others do not. A piece that more bars disagree with than agree is wrong. This holds at the
    start and end of the data, and for a wrong stretch almost as long as the window."""

    if frame.empty:
        return frame
    bad = []
    for _, rows in frame.assign(trade_date=pd.to_datetime(frame["trade_date"])).groupby("symbol"):
        rows = rows.sort_values("trade_date")
        close = pd.to_numeric(rows["raw_close"], errors="coerce").reset_index(drop=True)
        cuts = (close / close.shift(1) - 1).abs() > MAX_INDEX_MOVE
        piece = cuts.cumsum()
        for number in piece.unique():
            inside = piece[piece == number].index
            level = close.iloc[inside].median()
            if not level or pd.isna(level):
                continue
            window = close.iloc[max(0, inside[0] - context):inside[-1] + 1 + context].dropna()
            ratio = window / level
            agree = int(((ratio <= factor) & (ratio >= 1 / factor)).sum())
            if len(window) - agree > agree:
                bad.append(rows.iloc[list(inside)])
    found = [part for part in bad if not part.empty]
    return pd.concat(found) if found else frame.iloc[0:0]


def describe(rows: pd.DataFrame) -> str:
    """``000001.SH 2026-09-10 至 2026-10-08（15 天）``, one per index, for messages and logs."""

    parts = []
    for symbol, group in rows.groupby("symbol"):
        days = pd.to_datetime(group["trade_date"])
        parts.append(f"{symbol} {days.min().date()} 至 {days.max().date()}（{len(group)} 天）")
    return "；".join(parts)
