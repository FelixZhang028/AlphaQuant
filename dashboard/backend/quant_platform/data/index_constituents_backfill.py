"""Download the history of index constituents from BaoStock.

One request returns an index's members on a day; the vendor refreshes them every Monday. Members
change a few times a year, so instead of asking for every week the range is cut into half-year
pieces, each piece's two ends are compared, and only pieces whose ends differ are searched (by
halving) for the weeks in which the list changed. Twelve years of three indexes is a few hundred
requests of one or two seconds each. A later run only checks the weeks after the last one checked.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd

from quant_platform.core.exceptions import DataSourceBlocked, DataUnavailableError
from quant_platform.data.index_constituents import (
    CHECKS_TABLE,
    CONSTITUENTS_TABLE,
    INDEX_UNIVERSES,
    checked_range,
    index_name,
    members_on,
    normalize_baostock_constituents,
    stored_lists,
    week_start,
)
from quant_platform.data.providers.baostock_provider import BaoStockDataProvider
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository

logger = logging.getLogger(__name__)

STAGE = "index_constituents"
PIECE_WEEKS = 26
ProgressCallback = Callable[[str, int, int], None]
Piece = tuple[str, date, date]


def _pieces(first: date, last: date) -> list[tuple[date, date]]:
    """Cut the Mondays from ``first`` to ``last`` into consecutive pieces, oldest first."""

    pieces = []
    while first < last:
        upper = min(first + timedelta(weeks=PIECE_WEEKS), last)
        pieces.append((first, upper))
        first = upper
    return pieces


class BaoStockIndexConstituentsBackfill:
    """Find the weeks in which each index's member list changed and store the list at each."""

    def __init__(self, market_repository: ParquetMarketDataRepository, provider: BaoStockDataProvider | Any | None = None,
                 today: date | None = None) -> None:
        self.market_repository = market_repository
        self.provider = provider or BaoStockDataProvider()
        self.today = today or date.today()
        self.requests = 0

    def plan(self, start_date: date, end_date: date, indexes: list[str] | None = None) -> list[Piece]:
        """The pieces not checked yet, in the order they run.

        Each index's checked dates stay one unbroken range: pieces after it run oldest first,
        pieces before it run newest first, so an interrupted run never leaves a gap.
        """

        checks = self.market_repository.read_table(CHECKS_TABLE)
        first, last = week_start(start_date), week_start(min(end_date, self.today))
        plan: list[Piece] = []
        for index_symbol in indexes or list(INDEX_UNIVERSES):
            if index_symbol not in INDEX_UNIVERSES:
                raise ValueError(f"不支持的指数：{index_symbol}")
            covered = checked_range(checks, index_symbol)
            if covered is None:
                # 第一次：只有一周时也要取这一周的名单。
                plan.extend((index_symbol, lower, upper) for lower, upper in (_pieces(first, last) or [(first, first)]))
                continue
            plan.extend((index_symbol, lower, upper) for lower, upper in _pieces(covered[1], last))
            plan.extend((index_symbol, lower, upper) for lower, upper in reversed(_pieces(first, covered[0])))
        return plan

    def backfill(self, start_date: date, end_date: date, *, indexes: list[str] | None = None,
                 progress: ProgressCallback | None = None) -> dict[str, Any]:
        """Check the planned pieces; when one fails the rest of that index waits for the next run."""

        plan = self.plan(start_date, end_date, indexes)
        failed: dict[str, str] = {}
        changes = 0
        self.requests = 0
        if progress:
            progress(STAGE, 0, len(plan))
        if not plan:
            return {"requests": 0, "changes": 0, "failed": failed}
        try:
            self.provider.login()
            for done, (index_symbol, lower, upper) in enumerate(plan, start=1):
                if not any(key.startswith(index_symbol) for key in failed):
                    try:
                        changes += self._check(index_symbol, lower, upper)
                    except DataSourceBlocked:  # 数据源拒绝了这台服务器：整个任务停下，不再逐只重试
                        raise
                    except Exception as exc:  # noqa: BLE001 - 一个指数失败不影响其他指数
                        failed[f"{index_symbol} {lower}~{upper}"] = f"{type(exc).__name__}: {exc}"[:300]
                        logger.warning("%s成分股下载失败：%s ~ %s（%s）", index_name(index_symbol), lower, upper, exc)
                if progress:
                    progress(STAGE, done, len(plan))
        finally:
            self.provider.close()
        return {"requests": self.requests, "changes": changes, "failed": failed}

    def _check(self, index_symbol: str, lower: date, upper: date) -> int:
        """Store the lists that changed between two Mondays and widen the checked range to them."""

        checks = self.market_repository.read_table(CHECKS_TABLE)
        covered = checked_range(checks, index_symbol)
        lists = stored_lists(self.market_repository.read_table(CONSTITUENTS_TABLE), index_symbol)
        found: dict[date, frozenset[str]] = {}

        def at(day: date) -> frozenset[str]:
            # 已经核对过的日期用保存的名单，不再请求。
            if covered and covered[0] <= day <= covered[1]:
                known = members_on(lists, day)
                if known is not None:
                    return known
            return self._fetch(index_symbol, day)

        def changed(start: date, before: frozenset[str], end: date, after: frozenset[str]) -> None:
            if before == after:
                return
            weeks = (end - start).days // 7
            if weeks <= 1:
                found[end] = after
                return
            middle = start + timedelta(weeks=weeks // 2)
            between = self._fetch(index_symbol, middle)
            changed(start, before, middle, between)
            changed(middle, between, end, after)

        first_list = at(lower)
        if covered is None or lower < covered[0]:
            found[lower] = first_list   # 核对范围里最早的一天：从这一天起才知道成分股
        changed(lower, first_list, upper, first_list if upper == lower else at(upper))
        rows = [
            normalize_baostock_constituents(pd.DataFrame({"code": sorted(members)}), index_symbol, day)
            for day, members in sorted(found.items()) if lists.get(day) != members
        ]
        if rows:
            self.market_repository.save_table(CONSTITUENTS_TABLE, pd.concat(rows, ignore_index=True))
        self.market_repository.save_table(CHECKS_TABLE, pd.DataFrame([{
            "index_symbol": index_symbol,
            "checked_from": pd.Timestamp(min(lower, covered[0]) if covered else lower),
            "checked_through": pd.Timestamp(max(upper, covered[1]) if covered else upper),
            "updated_at": datetime.now(UTC),
        }]))
        return len(rows)

    def _fetch(self, index_symbol: str, day: date) -> frozenset[str]:
        self.requests += 1
        frame = self.provider.get_index_constituents(INDEX_UNIVERSES[index_symbol][1], day)
        members = frozenset(normalize_baostock_constituents(frame, index_symbol, day)["symbol"])
        if not members:
            raise DataUnavailableError(f"{index_name(index_symbol)}在 {day} 没有成分股数据")
        return members
