"""Download the history of industry classifications from BaoStock, one market-wide snapshot per quarter.

One request returns every stock's industry as of a day. Classifications change slowly (a few
percent of stocks a year), so a snapshot at each quarter end plus today's is enough; a run is a
few dozen requests of roughly half a minute each. Dates already fetched are not asked again.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from quant_platform.core.exceptions import DataSourceBlocked

from quant_platform.data.fundamentals import quarter_end, quarters_between
from quant_platform.data.industry import (
    EXPOSURES_TABLE,
    SNAPSHOTS_TABLE,
    new_change_points,
    normalize_baostock_industry,
)
from quant_platform.data.providers.baostock_provider import BaoStockDataProvider
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository

logger = logging.getLogger(__name__)

STAGE = "industry"
ProgressCallback = Callable[[str, int, int], None]


class BaoStockIndustryBackfill:
    """Fetch the snapshots not fetched yet and keep the change points."""

    def __init__(self, market_repository: ParquetMarketDataRepository, provider: BaoStockDataProvider | Any | None = None,
                 today: date | None = None) -> None:
        self.market_repository = market_repository
        self.provider = provider or BaoStockDataProvider()
        self.today = today or date.today()

    def plan(self, start_date: date, end_date: date) -> list[date]:
        """Quarter ends in the range plus the last day asked for, oldest first, minus what is stored."""

        last = min(end_date, self.today)
        wanted = {quarter_end(year, quarter) for year, quarter in quarters_between(start_date, last)} | {last}
        log = self.market_repository.read_table(SNAPSHOTS_TABLE)
        done = set(pd.to_datetime(log["requested_date"]).dt.date) if not log.empty else set()
        # 最新的那一张每次都重新取：它之后可能已经有新的分类。
        return sorted(day for day in wanted if day not in done or day == last)

    def backfill(self, start_date: date, end_date: date, *, progress: ProgressCallback | None = None) -> dict[str, Any]:
        """Fetch the planned snapshots in date order; a failed snapshot is reported and retried next run."""

        days = self.plan(start_date, end_date)
        failed: dict[str, str] = {}
        stored = fetched = 0
        if progress:
            progress(STAGE, 0, len(days))
        if not days:
            return {"snapshots": 0, "changes": 0, "failed": failed}
        try:
            self.provider.login()
            for index, day in enumerate(days, start=1):
                try:
                    snapshot = normalize_baostock_industry(self.provider.get_industry_snapshot(day))
                    changes = new_change_points(self.market_repository.read_table(EXPOSURES_TABLE), snapshot)
                    self.market_repository.save_table(EXPOSURES_TABLE, changes)
                    self.market_repository.save_table(SNAPSHOTS_TABLE, pd.DataFrame([{
                        "requested_date": pd.Timestamp(day),
                        "update_date": snapshot["date"].max() if not snapshot.empty else pd.NaT,
                        "rows": len(snapshot), "changes": len(changes), "fetched_at": datetime.now(UTC),
                    }]))
                    stored += len(changes)
                    fetched += 1
                except DataSourceBlocked:  # 数据源拒绝了这台服务器：整个任务停下，不再逐只重试
                    raise
                except Exception as exc:  # noqa: BLE001 - 一张快照失败不影响其余日期
                    failed[day.isoformat()] = f"{type(exc).__name__}: {exc}"[:300]
                    logger.warning("行业分类快照下载失败：%s（%s）", day, exc)
                if progress:
                    progress(STAGE, index, len(days))
        finally:
            self.provider.close()
        return {"snapshots": fetched, "changes": stored, "failed": failed}
