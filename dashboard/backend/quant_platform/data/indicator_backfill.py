"""Fill in the daily valuation and turnover indicators for bars that are already stored.

New bars bring their indicators with them (BaoStock returns both in one request). This is for
the history downloaded before that, and for bars that came from a source without indicators:
one small request per stock, no prices re-read, nothing in ``daily_bars`` touched.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pandas as pd

from quant_platform.core.exceptions import DataUnavailableError
from quant_platform.data.indicators import INDICATOR_TABLE, normalize_baostock_indicators
from quant_platform.data.providers.baostock_provider import BaoStockDataProvider
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository

logger = logging.getLogger(__name__)

STAGE = "daily_indicators"
# 连续这么多只股票取不到数据时，认为是数据源出了问题，停下来而不是把剩下的都记成失败。
CONSECUTIVE_FAILURE_LIMIT = 10
ProgressCallback = Callable[[str, int, int], None]


def missing_ranges(first: date, last: date, stored_start: date | None, stored_end: date | None) -> list[tuple[date, date]]:
    """The parts of ``[first, last]`` not covered by the stored span (which is assumed contiguous)."""

    if first > last:
        return []
    if stored_start is None or stored_end is None or stored_end < first or stored_start > last:
        return [(first, last)]
    ranges = []
    if first < stored_start:
        ranges.append((first, stored_start - timedelta(days=1)))
    if last > stored_end:
        ranges.append((stored_end + timedelta(days=1), last))
    return ranges


class BaoStockIndicatorBackfill:
    """Download indicators only for the dates a stock has bars but no indicators yet."""

    def __init__(self, market_repository: ParquetMarketDataRepository, provider: BaoStockDataProvider | Any | None = None) -> None:
        self.market_repository = market_repository
        self.provider = provider or BaoStockDataProvider()

    def plan(self, start_date: date, end_date: date, symbols: list[str] | None = None) -> list[tuple[str, list[tuple[date, date]]]]:
        """Per stock, the date ranges to request: inside its stored bars, outside its stored indicators."""

        bars = self.market_repository.daily_bar_summary()
        stored = self.market_repository.daily_indicator_spans()
        work = []
        for symbol in (symbols if symbols is not None else list(bars.index)):
            if symbol not in bars.index:
                continue
            first = max(start_date, bars.at[symbol, "start"].date())
            last = min(end_date, bars.at[symbol, "end"].date())
            span = (stored.at[symbol, "start"].date(), stored.at[symbol, "end"].date()) if symbol in stored.index else (None, None)
            ranges = missing_ranges(first, last, *span)
            if ranges:
                work.append((symbol, ranges))
        return work

    def backfill(
        self, start_date: date, end_date: date, *, symbols: list[str] | None = None,
        batch_size: int = 50, progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Fetch and store the missing indicators; one stock failing does not stop the rest.

        Stocks are saved in batches, so an interrupted run keeps what it finished and the next
        run only requests what is still missing.
        """

        work = self.plan(start_date, end_date, symbols)
        total = len(work)
        failed: dict[str, str] = {}
        frames: list[pd.DataFrame] = []
        rows = done = consecutive_failures = 0
        if progress:
            progress(STAGE, 0, total)
        if not work:
            return {"symbols": 0, "updated": 0, "rows": 0, "failed": failed}
        try:
            # 先登录一次：数据源连不上时立刻说明，而不是让每只股票各失败一遍。
            self.provider.login()
            for symbol, ranges in work:
                try:
                    for first, last in ranges:
                        frame = normalize_baostock_indicators(self.provider.get_indicator_range(symbol, first, last))
                        if not frame.empty:
                            frames.append(frame)
                    consecutive_failures = 0
                except Exception as exc:  # noqa: BLE001 - 单只失败不阻断其余股票
                    consecutive_failures += 1
                    failed[symbol] = f"{type(exc).__name__}: {exc}"[:300]
                    logger.warning("估值与换手率回填失败：%s（%s）", symbol, exc)
                    if consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
                        rows += self._flush(frames)
                        raise DataUnavailableError(
                            f"连续 {CONSECUTIVE_FAILURE_LIMIT} 只股票取不到估值与换手率，数据源可能暂时不可用；已保存的部分不会丢失，稍后重新运行即可继续。"
                        ) from exc
                done += 1
                if len(frames) >= batch_size:
                    rows += self._flush(frames)
                if progress:
                    progress(STAGE, done, total)
            rows += self._flush(frames)
        finally:
            self.provider.close()
        return {"symbols": total, "updated": total - len(failed), "rows": rows, "failed": failed}

    def _flush(self, frames: list[pd.DataFrame]) -> int:
        if not frames:
            return 0
        batch = pd.concat(frames, ignore_index=True)
        frames.clear()
        self.market_repository.save_table(INDICATOR_TABLE, batch)
        return len(batch)
