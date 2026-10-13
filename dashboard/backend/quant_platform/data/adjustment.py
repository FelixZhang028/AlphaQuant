"""Keep adjustment factors on one basis when bars are updated a window at a time.

Providers report forward-adjusted prices relative to the last day of each request, so
``adj_factor = adjusted_close / raw_close`` from two requests with different end dates
differs by a constant multiple. Stored as-is, the seam looks like a corporate action
that never happened: adjusted prices jump there and the backtest engine refuses to
value positions across it.

Providers also disagree on the method itself. BaoStock scales earlier prices by a ratio,
so its factor is constant between ex-dates; AkShare subtracts the dividend, so the same
ratio drifts with the price every day. No rescaling reconciles the two, which is why a
stock's adjusted history must keep coming from the provider it already came from.
"""

from __future__ import annotations

from datetime import date
from typing import Any, NamedTuple

import pandas as pd

from quant_platform.core.exceptions import DataUnavailableError

KEYS = ["symbol", "trade_date"]


class Alignment(NamedTuple):
    """Bars safe to save, and the symbols whose rows were withheld with the reason why."""

    bars: pd.DataFrame
    unaligned: list[str]
    source_changed: dict[str, tuple[str, str]]


class AdjustmentSourceChanged(DataUnavailableError):
    """Every incoming row would continue a stored history with another provider's method."""


def align_adjustment_basis(
    incoming: pd.DataFrame, stored: pd.DataFrame, symbols_with_history: set[str]
) -> Alignment:
    """Rescale incoming factors to the basis already stored for each symbol.

    ``stored`` holds the bars already saved on the incoming dates. The earliest date
    carrying a valid factor on both sides is the anchor: it ties the new rows to the
    history before the window, which this update does not rewrite.

    Rows are withheld, never saved on a guess, in two cases. ``unaligned``: the symbol
    is in ``symbols_with_history`` (it has adjusted bars before the window) yet shares
    no anchor day. ``source_changed``: the anchor was stored by a different provider,
    mapped to ``(stored, incoming)``. Symbols without stored factors, or without incoming
    factors, pass through unchanged.
    """

    if incoming.empty or "adj_factor" not in incoming.columns:
        return Alignment(incoming, [], {})
    result = incoming.copy()
    result["trade_date"] = pd.to_datetime(result["trade_date"]).dt.normalize()
    factor = pd.to_numeric(result["adj_factor"], errors="coerce")
    has_factor = factor.gt(0)
    fresh = result.loc[has_factor, KEYS].assign(incoming_factor=factor[has_factor])
    labelled = "source" in result.columns and "source" in stored.columns
    if labelled:
        fresh["incoming_source"] = result.loc[has_factor, "source"].astype("string")

    anchors = pd.DataFrame(columns=["symbol", "trade_date", "scale"])
    if not stored.empty and "adj_factor" in stored.columns:
        saved = stored[KEYS].copy()
        saved["trade_date"] = pd.to_datetime(saved["trade_date"]).dt.normalize()
        saved["stored_factor"] = pd.to_numeric(stored["adj_factor"], errors="coerce")
        if labelled:
            saved["stored_source"] = stored["source"].astype("string")
        shared = fresh.merge(saved[saved["stored_factor"].gt(0)], on=KEYS)
        anchors = shared.sort_values("trade_date").drop_duplicates("symbol", keep="first")
        anchors = anchors.assign(scale=anchors["stored_factor"] / anchors["incoming_factor"])

    anchored = anchors.set_index("symbol")
    source_changed: dict[str, tuple[str, str]] = {}
    if labelled and not anchored.empty:
        differs = anchored["stored_source"].notna() & anchored["stored_source"].ne(anchored["incoming_source"])
        source_changed = {
            str(symbol): (str(row.stored_source), str(row.incoming_source))
            for symbol, row in anchored[differs].iterrows()
        }
        anchored = anchored[~differs]
    unaligned = sorted(
        set(fresh["symbol"])
        .intersection(symbols_with_history)
        .difference(anchored.index)
        .difference(source_changed)
    )
    result = result[~result["symbol"].isin([*unaligned, *source_changed])].copy()
    scale = result["symbol"].map(anchored["scale"])
    rows = scale.notna()
    if rows.any():
        for column in ("adj_factor", "adjusted_close"):
            if column in result.columns:
                values = pd.to_numeric(result[column], errors="coerce")
                result[column] = values.where(~rows, values * scale)
        if "adjustment_source" in result.columns:
            anchor_day = result["symbol"].map(anchored["trade_date"]).dt.strftime("%Y-%m-%d")
            tagged = result["adjustment_source"].astype("string") + ";continuity_anchor=" + anchor_day
            result["adjustment_source"] = result["adjustment_source"].where(~rows, tagged)
    return Alignment(result, unaligned, source_changed)


class ContinuousAdjustmentRepository:
    """Repository view that aligns daily bars to the stored basis before saving them."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository
        self.unaligned: list[str] = []
        self.source_changed: dict[str, tuple[str, str]] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._repository, name)

    def save_table(self, name: str, frame: pd.DataFrame) -> None:
        if name != "daily_bars" or frame.empty or "adj_factor" not in frame.columns:
            self._repository.save_table(name, frame)
            return
        days = pd.to_datetime(frame["trade_date"])
        first, last = days.min().date(), days.max().date()
        symbols = sorted(frame["symbol"].astype(str).unique())
        stored = self._repository.get_daily_bars(symbols, first, last)
        history = self._repository.last_adjusted_bar_dates(symbols, before=first)
        aligned = align_adjustment_basis(frame, stored, set(history))
        self.unaligned = sorted(set(self.unaligned).union(aligned.unaligned))
        self.source_changed.update(aligned.source_changed)
        if aligned.bars.empty:
            if aligned.source_changed and not aligned.unaligned:
                raise AdjustmentSourceChanged(source_changed_message(aligned.source_changed))
            raise DataUnavailableError(unaligned_message(aligned.unaligned, history))
        self._repository.save_table(name, aligned.bars)


def _preview(symbols: list[str]) -> str:
    return "、".join(symbols[:5]) + (" 等" if len(symbols) > 5 else "")


def unaligned_message(symbols: list[str], history: dict[str, date]) -> str:
    """Tell the user which start date would let the update overlap what is stored."""

    known = [history[symbol] for symbol in symbols if symbol in history]
    hint = f"请把开始日期提前到 {min(known).isoformat()} 或更早后重试" if known else "请提前开始日期后重试"
    return (
        f"{len(symbols)} 只股票的新行情与本地已有行情没有重叠的交易日，"
        f"复权因子无法对齐，未写入（{_preview(symbols)}）。{hint}。"
    )


def source_changed_message(changed: dict[str, tuple[str, str]]) -> str:
    """Explain why another provider's rows were not appended to a stored history."""

    stored = "、".join(sorted({pair[0] for pair in changed.values()}))
    incoming = "、".join(sorted({pair[1] for pair in changed.values()}))
    return (
        f"{len(changed)} 只股票的历史行情来自 {stored}，不能用 {incoming} 的数据续接"
        f"（两个数据源计算前复权价格的方法不同），未写入（{_preview(sorted(changed))}）。"
    )
