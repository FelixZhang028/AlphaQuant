"""Adjustment-factor changes that no corporate-action record explains, and filling them from BaoStock.

A change in a stock's adjustment factor means a dividend, a bonus or transfer issue, a rights
issue or some other event happened that day. The backtest settles a held stock's events from
``corporate_actions`` (cash and new shares); a change without a record cannot be settled that way.

Most such changes belong to delisted stocks, for which the usual source (AkShare, from East Money)
returns nothing. BaoStock's dividend endpoint still has them, one request per stock and year.
Rights issues are in neither source; the engine handles those itself and reports them.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import numpy as np
import pandas as pd

from quant_platform.core.exceptions import DataSourceBlocked

from quant_platform.data.normalizers import canonical_symbol

logger = logging.getLogger(__name__)

STAGE = "corporate_action_gaps"
CHECKS_TABLE = "corporate_action_checks"
CHANGE_COLUMNS = ["symbol", "trade_date", "previous_date", "ratio"]
ACTION_COLUMNS = ["symbol", "ex_date", "cash_per_share", "share_multiplier", "source", "ingested_at"]
CONSECUTIVE_FAILURE_LIMIT = 10
SAVE_EVERY = 20
ProgressCallback = Callable[[str, int, int], None]


def factor_changes(bars: pd.DataFrame) -> pd.DataFrame:
    """Each day a stock's adjustment factor differs from its previous valid one (the engine's tolerance)."""

    if bars.empty:
        return pd.DataFrame(columns=CHANGE_COLUMNS)
    frame = bars[["symbol", "trade_date", "adj_factor"]].copy()
    frame["adj_factor"] = pd.to_numeric(frame["adj_factor"], errors="coerce")
    frame = frame[frame["adj_factor"].gt(0)]
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.normalize()
    frame = frame.sort_values(["symbol", "trade_date"])
    grouped = frame.groupby("symbol", sort=False)
    previous, previous_date = grouped["adj_factor"].shift(), grouped["trade_date"].shift()
    changed = previous.notna() & ~np.isclose(previous, frame["adj_factor"], rtol=1e-7, atol=0)
    result = pd.DataFrame({
        "symbol": frame["symbol"][changed].astype(str),
        "trade_date": frame["trade_date"][changed],
        "previous_date": previous_date[changed],
        "ratio": (frame["adj_factor"] / previous)[changed],
    })
    return result.reset_index(drop=True)


def unexplained_changes(changes: pd.DataFrame, actions: pd.DataFrame) -> pd.DataFrame:
    """The changes with no record dated after the previous bar and on or before the change."""

    if changes.empty:
        return changes
    if actions.empty or not {"symbol", "ex_date"} <= set(actions.columns):
        return changes.reset_index(drop=True)
    records = pd.DataFrame({
        "symbol": actions["symbol"].astype(str),
        "ex_date": pd.to_datetime(actions["ex_date"]).dt.normalize(),
    }).dropna().sort_values("ex_date")
    ordered = changes.sort_values("trade_date").reset_index()
    matched = pd.merge_asof(ordered, records, left_on="trade_date", right_on="ex_date", by="symbol", direction="backward")
    explained = matched["ex_date"].notna() & (matched["ex_date"] > matched["previous_date"])
    keep = matched.loc[~explained, "index"]
    return changes.loc[sorted(keep)].reset_index(drop=True)


def normalize_baostock_dividends(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """BaoStock dividend rows -> corporate-action rows: pre-tax cash and bonus plus transfer shares, per share."""

    if frame.empty or "dividOperateDate" not in frame.columns:
        return pd.DataFrame(columns=ACTION_COLUMNS)

    def number(column: str) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(0.0, index=frame.index)
        return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)

    result = pd.DataFrame({
        "symbol": canonical_symbol(symbol),
        "ex_date": pd.to_datetime(frame["dividOperateDate"], errors="coerce").dt.normalize(),
        "cash_per_share": number("dividCashPsBeforeTax"),
        "share_multiplier": 1.0 + number("dividStocksPs") + number("dividReserveToStockPs"),
    })
    result = result[result["ex_date"].notna() & ((result["cash_per_share"] > 0) | (result["share_multiplier"] > 1))]
    if result.empty:
        return pd.DataFrame(columns=ACTION_COLUMNS)
    # 同一除权日的多次分配合并为一条，和 AkShare 的口径一样。
    merged = result.groupby(["symbol", "ex_date"], as_index=False).agg(
        cash_per_share=("cash_per_share", "sum"), share_multiplier=("share_multiplier", "prod"))
    merged["source"] = "baostock"
    merged["ingested_at"] = datetime.now(UTC)
    return merged[ACTION_COLUMNS]


class BaoStockDividendBackfill:
    """Ask BaoStock for the years in which a stock has unexplained factor changes; keep the rows that explain them."""

    def __init__(self, repository: Any, provider: Any | None = None) -> None:
        self.repository = repository
        if provider is None:
            from quant_platform.data.providers.baostock_provider import BaoStockDataProvider

            provider = BaoStockDataProvider()
        self.provider = provider

    def unexplained(self) -> pd.DataFrame:
        return unexplained_changes(self.repository.adj_factor_changes(), self.repository.read_table("corporate_actions"))

    def plan(self, today: date | None = None) -> dict[str, list[int]]:
        """Stock -> the years to ask about (the years of the previous bar and of the change).

        A past year already asked about is not asked again: the source had nothing more then
        and will not later. This year is always asked, since new records still appear.
        """

        this_year = (today or date.today()).year
        checks = self.repository.read_table(CHECKS_TABLE)
        asked = set(zip(checks["symbol"].astype(str), checks["year"].astype(int))) if not checks.empty else set()
        gaps = self.unexplained()
        plan: dict[str, set[int]] = {}
        for symbol, previous, day in zip(gaps["symbol"], gaps["previous_date"], gaps["trade_date"], strict=True):
            years = range(pd.Timestamp(previous).year, pd.Timestamp(day).year + 1)
            wanted = {year for year in years if year >= this_year or (symbol, year) not in asked}
            if wanted:
                plan.setdefault(symbol, set()).update(wanted)
        return {symbol: sorted(years) for symbol, years in sorted(plan.items())}

    def backfill(self, *, progress: ProgressCallback | None = None) -> dict[str, Any]:
        gaps = self.unexplained()
        plan = self.plan()
        failed: dict[str, str] = {}
        added: list[pd.DataFrame] = []
        stored = requests = consecutive_failures = 0
        if progress:
            progress(STAGE, 0, len(plan))
        if not plan:
            return {"requests": 0, "added": 0, "failed": failed, "unexplained_before": 0, "unexplained_after": 0}
        windows = {symbol: group[["previous_date", "trade_date"]] for symbol, group in gaps.groupby("symbol")}
        checked: list[dict[str, Any]] = []
        try:
            self.provider.login()
            for done, (symbol, years) in enumerate(plan.items(), start=1):
                try:
                    frames = []
                    for year in years:
                        requests += 1
                        frames.append(self.provider.get_dividends(symbol, year))
                    rows = normalize_baostock_dividends(pd.concat(frames, ignore_index=True), symbol)
                    # 只要能解释一次没有记录的变化的那几行，不改动已有的记录。
                    window = windows[symbol]
                    useful = rows["ex_date"].map(
                        lambda day: bool(((window["previous_date"] < day) & (day <= window["trade_date"])).any()))
                    added.append(rows[useful.astype(bool)])
                    checked.extend({"symbol": symbol, "year": year, "checked_at": datetime.now(UTC)} for year in years)
                    consecutive_failures = 0
                except DataSourceBlocked:  # 数据源拒绝了这台服务器：整个任务停下，不再逐只重试
                    raise
                except Exception as exc:  # noqa: BLE001 - 一只失败不影响其他股票
                    consecutive_failures += 1
                    failed[symbol] = f"{type(exc).__name__}: {exc}"[:300]
                    logger.warning("分红送转记录下载失败：%s（%s）", symbol, exc)
                    if consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
                        break
                if done % SAVE_EVERY == 0:
                    stored += self._save(added, checked)
                    added, checked = [], []
                if progress:
                    progress(STAGE, done, len(plan))
            stored += self._save(added, checked)
        finally:
            self.provider.close()
        return {
            "requests": requests,
            "added": stored,
            "failed": failed,
            "unexplained_before": int(len(gaps)),
            "unexplained_after": int(len(self.unexplained())),
        }

    def _save(self, frames: list[pd.DataFrame], checked: list[dict[str, Any]]) -> int:
        rows = [frame for frame in frames if not frame.empty]
        combined = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
        if not combined.empty:
            self.repository.save_table("corporate_actions", combined)
        if checked:
            self.repository.save_table(CHECKS_TABLE, pd.DataFrame(checked))
        return len(combined)
