"""Download quarterly financial reports from BaoStock, one stock and one quarter at a time.

BaoStock answers one (stock, year, quarter) per request and a row takes three requests
(profit, growth, balance sheet). Twelve years of one stock is about 150 requests, so the whole
market takes hours while a stock pool takes seconds to minutes. Runs are resumable: periods
already stored are not requested again, and what is fetched is saved in batches.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pandas as pd

from quant_platform.core.exceptions import DataUnavailableError
from quant_platform.data.fundamentals import (
    BAOSTOCK_FUNDAMENTAL_FIELDS,
    FUNDAMENTALS_TABLE,
    STORED_COLUMNS,
    checked_empty_row,
    normalize_baostock_quarter,
    quarter_end,
    quarters_between,
)
from quant_platform.data.providers.baostock_provider import BaoStockDataProvider
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository

logger = logging.getLogger(__name__)

STAGE = "quarterly_fundamentals"
CONSECUTIVE_FAILURE_LIMIT = 10
# 上市前一年的财报也取：同比增长要用到上一年的数。
LEAD_DAYS = 366
# 季度结束超过这么久还没有财报，就认为这一期不会有了，记下来不再询问。
SETTLED_AFTER_DAYS = 365
ProgressCallback = Callable[[str, int, int], None]


class BaoStockFundamentalsBackfill:
    """Fetch the reporting periods a stock has bars for but no stored report yet."""

    def __init__(self, market_repository: ParquetMarketDataRepository, provider: BaoStockDataProvider | Any | None = None,
                 today: date | None = None) -> None:
        self.market_repository = market_repository
        self.provider = provider or BaoStockDataProvider()
        self.today = today or date.today()

    def plan(self, start_date: date, end_date: date, symbols: list[str] | None = None) -> list[tuple[str, list[tuple[int, int]]]]:
        """Per stock, the (year, quarter) periods to request."""

        bars = self.market_repository.daily_bar_summary()
        stored = self.market_repository.get_fundamentals(symbols)
        have: dict[str, set[date]] = {}
        for symbol, day in zip(stored["symbol"], pd.to_datetime(stored["stat_date"]), strict=True):
            have.setdefault(str(symbol), set()).add(day.date())
        last = min(end_date, self.today)
        work = []
        for symbol in (symbols if symbols is not None else list(bars.index)):
            if symbol not in bars.index:
                continue
            first = max(start_date, bars.at[symbol, "start"].date() - timedelta(days=LEAD_DAYS))
            known = have.get(symbol, set())
            periods = [(year, quarter) for year, quarter in quarters_between(first, last) if quarter_end(year, quarter) not in known]
            if periods:
                work.append((symbol, periods))
        return work

    def backfill(
        self, start_date: date, end_date: date, *, symbols: list[str] | None = None,
        batch_size: int = 20, progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Fetch and store the missing reports; one stock failing does not stop the rest."""

        work = self.plan(start_date, end_date, symbols)
        total = len(work)
        failed: dict[str, str] = {}
        rows: list[dict] = []
        reports = done = pending_symbols = consecutive_failures = 0
        if progress:
            progress(STAGE, 0, total)
        if not work:
            return {"symbols": 0, "updated": 0, "reports": 0, "failed": failed}
        try:
            # 先登录一次：数据源连不上时立刻说明，而不是让每只股票各失败一遍。
            self.provider.login()
            for symbol, periods in work:
                try:
                    fetched = [self._fetch(symbol, year, quarter) for year, quarter in periods]
                    rows.extend(row for row in fetched if row is not None)
                    reports += sum(1 for row in fetched if row is not None and pd.notna(row["pub_date"]))
                    consecutive_failures = 0
                except Exception as exc:  # noqa: BLE001 - 单只失败不阻断其余股票
                    consecutive_failures += 1
                    failed[symbol] = f"{type(exc).__name__}: {exc}"[:300]
                    logger.warning("财务数据下载失败：%s（%s）", symbol, exc)
                    if consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
                        self._flush(rows)
                        raise DataUnavailableError(
                            f"连续 {CONSECUTIVE_FAILURE_LIMIT} 只股票取不到财务数据，数据源可能暂时不可用；已保存的部分不会丢失，稍后重新运行即可继续。"
                        ) from exc
                done += 1
                pending_symbols += 1
                if pending_symbols >= batch_size:
                    self._flush(rows)
                    pending_symbols = 0
                if progress:
                    progress(STAGE, done, total)
            self._flush(rows)
        finally:
            self.provider.close()
        return {"symbols": total, "updated": total - len(failed), "reports": reports, "failed": failed}

    def _fetch(self, symbol: str, year: int, quarter: int) -> dict | None:
        """One stored row for a period, a checked-empty marker for an old gap, or nothing for a recent gap."""

        responses: dict[str, pd.DataFrame] = {}
        for endpoint in BAOSTOCK_FUNDAMENTAL_FIELDS:
            responses[endpoint] = self.provider.get_quarterly_report(endpoint, symbol, year, quarter)
            if endpoint == "profit" and responses[endpoint].empty:
                break  # 没有利润表就是这一期没有财报，不用再问另外两张表
        row = normalize_baostock_quarter(symbol, year, quarter, responses)
        if row is not None:
            return row
        settled = quarter_end(year, quarter) < self.today - timedelta(days=SETTLED_AFTER_DAYS)
        return checked_empty_row(symbol, year, quarter) if settled else None

    def _flush(self, rows: list[dict]) -> None:
        if not rows:
            return
        batch = pd.DataFrame(rows, columns=STORED_COLUMNS)
        rows.clear()
        self.market_repository.save_table(FUNDAMENTALS_TABLE, batch)
