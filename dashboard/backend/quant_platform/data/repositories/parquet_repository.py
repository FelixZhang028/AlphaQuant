"""Local Parquet repository with key-based upserts and date partitions."""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from threading import RLock

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from quant_platform.core.files import replace_file
from quant_platform.data.fundamentals import (
    FUNDAMENTAL_COLUMNS,
    FUNDAMENTALS_TABLE,
    STORED_COLUMNS,
    point_in_time,
)
from quant_platform.data.indicators import INDICATOR_COLUMNS, INDICATOR_TABLE
from quant_platform.data.industry import EXPOSURES_TABLE, INDUSTRY_COLUMNS, industry_on
from quant_platform.data.interfaces import MarketDataRepository
from quant_platform.data.normalizers import CANONICAL_BAR_COLUMNS

_TABLE_KEYS: dict[str, list[str]] = {
    "daily_bars": ["symbol", "trade_date"],
    INDICATOR_TABLE: ["symbol", "trade_date"],
    FUNDAMENTALS_TABLE: ["symbol", "stat_date"],
    "trade_calendar": ["cal_date"],
    "security_master": ["symbol"],
    "corporate_actions": ["symbol", "ex_date"],
    "universe_membership": ["symbol", "effective_from"],
    "security_exposures": ["symbol", "date"],
    "industry_snapshots": ["requested_date"],
    "index_constituents": ["index_symbol", "effective_date", "symbol"],
    "index_constituent_checks": ["index_symbol"],
    "corporate_action_checks": ["symbol", "year"],
    "delisting_settlements": ["symbol"],
}

# ``daily_bars`` and the daily indicators that go with it grow to millions of rows, so
# they are partitioned by calendar year. Every other canonical table stays in one file.
_PARTITIONED_TABLES = frozenset({"daily_bars", INDICATOR_TABLE})
_PARTITION_COLUMN = "year"
# 上次写到一半被结束留下的临时文件，过了这么久就清掉。
_STALE_TEMPORARY_SECONDS = 3600


def write_parquet_atomic(frame: pd.DataFrame, path: Path) -> None:
    """Write ``frame`` to ``path`` so that no reader, crash or killed process ever sees half a file.

    The new file is written beside the old one under a name starting with ``.`` (Parquet
    datasets skip such files and ``*.parquet`` globs do not match them), then swapped in with
    one rename. A process stopped in the middle leaves the old file intact and a stray
    temporary that a later write removes.
    """

    path = Path(path)
    for stale in path.parent.glob(f".{path.name}.*.tmp"):
        try:
            if time.time() - stale.stat().st_mtime > _STALE_TEMPORARY_SECONDS:
                stale.unlink()
        except OSError:
            pass
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        frame.to_parquet(temporary, index=False)
        replace_file(temporary, path)     # Windows 上旧文件正被别的进程读着时，等它读完再替换
    finally:
        temporary.unlink(missing_ok=True)


class ParquetMarketDataRepository(MarketDataRepository):
    """Persist canonical market tables as local Parquet files or partitions."""

    def __init__(self, root: str | Path) -> None:
        # resolve() 隔离不同工作目录下的相对路径缓存，避免跨目录读到同一张表。
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _flat_path(self, name: str) -> Path:
        return self.root / f"{name}.parquet"

    def _partition_path(self, name: str) -> Path:
        return self.root / name

    def save_table(self, name: str, frame: pd.DataFrame) -> None:
        """Upsert a table using its canonical natural key."""

        if frame.empty:
            return
        if name in _PARTITIONED_TABLES:
            self._save_partitioned(name, frame)
        else:
            self._save_flat(name, frame)

    def read_table(self, name: str) -> pd.DataFrame:
        """Read a canonical table or return an empty frame if absent."""

        if name in _PARTITIONED_TABLES:
            return self._read_partitioned(name)
        return self._read_flat(name)

    def get_daily_bars(
        self,
        symbols: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        *,
        extras: Iterable[str] = (),
    ) -> pd.DataFrame:
        """Daily bars; ``extras`` names further columns to attach to each bar.

        Valuation and turnover indicators are matched on the day. Financial-report columns are
        matched point in time: each bar gets the newest report already published that day.
        ``industry`` / ``sector`` are the classification in force that day.
        A bar without a value keeps the bar and gets a missing value.
        """

        bars = self._get_daily_bars(symbols, start_date, end_date)
        asked = set(extras)
        daily = [column for column in INDICATOR_COLUMNS if column in asked]
        quarterly = [column for column in FUNDAMENTAL_COLUMNS if column in asked]
        industry = [column for column in INDUSTRY_COLUMNS if column in asked]
        if not daily and not quarterly and not industry:
            return bars
        if bars.empty:
            return bars.reindex(columns=[*bars.columns, *daily, *quarterly, *industry])
        if industry:
            changes = self.read_table(EXPOSURES_TABLE)
            days = pd.DataFrame({"symbol": bars["symbol"].to_numpy(), "date": bars["trade_date"].to_numpy()})
            for column in industry:
                bars[column] = industry_on(days, changes, column).to_numpy()
        if daily:
            stored = self.get_daily_indicators(symbols, start_date, end_date, columns=daily)
            bars = bars.merge(stored, on=["symbol", "trade_date"], how="left")
        if quarterly:
            reports = self.get_fundamentals(symbols)
            matched = point_in_time(bars, reports, quarterly)
            for column in quarterly:
                bars[column] = matched[column].to_numpy()
        return bars

    def get_fundamentals(self, symbols: list[str] | None = None) -> pd.DataFrame:
        """Stored quarterly reports (one row per symbol and period), including checked-empty markers."""

        frame = self.read_table(FUNDAMENTALS_TABLE)
        if frame.empty:
            return pd.DataFrame(columns=STORED_COLUMNS)
        if symbols:
            frame = frame[frame["symbol"].isin(symbols)]
        return frame.sort_values(["symbol", "stat_date"]).reset_index(drop=True)

    def get_daily_indicators(
        self,
        symbols: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        *,
        columns: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        """Stored valuation and turnover indicators: symbol, trade_date and the requested columns."""

        wanted = [column for column in INDICATOR_COLUMNS if columns is None or column in set(columns)]
        frame = self._read_range(
            INDICATOR_TABLE, symbols=symbols, start_date=start_date, end_date=end_date,
            columns=["symbol", "trade_date", *wanted],
        )
        if frame.empty:
            return pd.DataFrame(columns=["symbol", "trade_date", *wanted])
        frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.normalize()
        return frame.reindex(columns=["symbol", "trade_date", *wanted]).sort_values(["trade_date", "symbol"]).reset_index(drop=True)

    def daily_indicator_spans(self) -> pd.DataFrame:
        """Per symbol: how many indicator rows are stored and over which dates (``rows``, ``start``, ``end``)."""

        directory, legacy = self._partition_path(INDICATOR_TABLE), self._flat_path(INDICATOR_TABLE)
        files = sorted(directory.rglob("*.parquet")) if self._has_partitions(directory) else ([legacy] if legacy.exists() else [])
        signature = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in files)
        key = f"{self.root.resolve()}|{INDICATOR_TABLE}"
        with _SUMMARY_LOCK:
            cached = _SUMMARY_CACHE.get(key)
            if cached is None or cached[0] != signature:
                frame = self._read_range(INDICATOR_TABLE, columns=["symbol", "trade_date"])
                if frame.empty:
                    spans = pd.DataFrame(columns=["rows", "start", "end"], index=pd.Index([], name="symbol"))
                else:
                    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.normalize()
                    spans = frame.groupby("symbol", sort=True)["trade_date"].agg(rows="size", start="min", end="max")
                cached = (signature, spans)
                _SUMMARY_CACHE[key] = cached
            return cached[1].copy()

    def _get_daily_bars(
        self,
        symbols: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pd.DataFrame:
        frame = self._read_daily_bars(symbols=symbols, start_date=start_date, end_date=end_date)
        if frame.empty:
            # 表缺失时返回带标准列的空表，避免下游 KeyError: 'trade_date'。
            return frame.reindex(columns=CANONICAL_BAR_COLUMNS)
        frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.normalize()
        mask = pd.Series(True, index=frame.index)
        if symbols:
            mask &= frame["symbol"].isin(symbols)
        if start_date:
            mask &= frame["trade_date"] >= pd.Timestamp(start_date)
        if end_date:
            mask &= frame["trade_date"] <= pd.Timestamp(end_date)
        return frame.loc[mask].sort_values(["trade_date", "symbol"]).reset_index(drop=True)

    def get_trade_calendar(self, start_date: date, end_date: date) -> pd.DataFrame:
        frame = self.read_table("trade_calendar")
        if frame.empty:
            return frame
        frame["cal_date"] = pd.to_datetime(frame["cal_date"]).dt.normalize()
        mask = frame["cal_date"].between(pd.Timestamp(start_date), pd.Timestamp(end_date))
        if "is_open" in frame.columns:
            mask &= frame["is_open"].astype(int).eq(1)
        return frame.loc[mask].sort_values("cal_date").reset_index(drop=True)

    def _save_flat(self, name: str, frame: pd.DataFrame) -> None:
        path = self._flat_path(name)
        combined = (
            pd.concat([pd.read_parquet(path), frame], ignore_index=True)
            if path.exists()
            else frame.copy()
        )
        combined = self._dedupe(combined, _TABLE_KEYS.get(name))
        write_parquet_atomic(combined, path)

    def _save_partitioned(self, name: str, frame: pd.DataFrame) -> None:
        directory = self._partition_path(name)
        legacy = self._flat_path(name)
        working = frame.copy()
        working["trade_date"] = pd.to_datetime(working["trade_date"]).dt.normalize()
        working[_PARTITION_COLUMN] = working["trade_date"].dt.year

        # Migrate a legacy single-file table on the first partitioned write.
        if legacy.exists() and not self._has_partitions(directory):
            legacy_frame = pd.read_parquet(legacy)
            legacy_frame["trade_date"] = pd.to_datetime(legacy_frame["trade_date"]).dt.normalize()
            legacy_frame[_PARTITION_COLUMN] = legacy_frame["trade_date"].dt.year
            working = pd.concat([legacy_frame, working], ignore_index=True)

        keys = _TABLE_KEYS.get(name)
        for year, group in working.groupby(_PARTITION_COLUMN, observed=True):
            partition = directory / f"{_PARTITION_COLUMN}={year}"
            if self._has_partitions(partition):
                existing = self._drop_partition_column(pd.read_parquet(partition))
                group = self._drop_partition_column(group)
                group = self._dedupe(pd.concat([existing, group], ignore_index=True), keys)
            else:
                group = self._drop_partition_column(group)
                group = self._dedupe(group, keys)
            partition.mkdir(parents=True, exist_ok=True)
            write_parquet_atomic(group, partition / "data.parquet")

        if legacy.exists() and self._has_partitions(directory):
            legacy.unlink()

    def _read_flat(self, name: str) -> pd.DataFrame:
        path = self._flat_path(name)
        return pd.read_parquet(path) if path.exists() else pd.DataFrame()

    def _read_partitioned(self, name: str) -> pd.DataFrame:
        directory = self._partition_path(name)
        legacy = self._flat_path(name)
        if self._has_partitions(directory):
            frame = pd.read_parquet(directory)
        elif legacy.exists():
            frame = pd.read_parquet(legacy)
        else:
            return pd.DataFrame()
        return self._drop_partition_column(frame)

    def _read_daily_bars(
        self, start_date: date | None = None, end_date: date | None = None,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        return self._read_range("daily_bars", symbols=symbols, start_date=start_date, end_date=end_date)

    def _read_range(
        self, name: str, *, symbols: list[str] | None = None, start_date: date | None = None,
        end_date: date | None = None, columns: list[str] | None = None,
    ) -> pd.DataFrame:
        """Rows of a year-partitioned table for some symbols and dates; ``columns`` limits what is read."""

        directory = self._partition_path(name)
        legacy = self._flat_path(name)
        filters = []
        if symbols:
            filters.append(("symbol", "in", symbols))
        if start_date:
            filters.append(("trade_date", ">=", pd.Timestamp(start_date)))
        if end_date:
            filters.append(("trade_date", "<", pd.Timestamp(end_date) + pd.Timedelta(days=1)))
        if self._has_partitions(directory):
            if start_date:
                filters.append((_PARTITION_COLUMN, ">=", start_date.year))
            if end_date:
                filters.append((_PARTITION_COLUMN, "<=", end_date.year))
            frame = pd.read_parquet(directory, filters=filters or None, columns=columns)
            return self._drop_partition_column(frame)
        if legacy.exists():
            return self._drop_partition_column(pd.read_parquet(legacy, filters=filters or None, columns=columns))
        return pd.DataFrame()

    def _daily_bar_files(self) -> list[Path]:
        directory, legacy = self._partition_path("daily_bars"), self._flat_path("daily_bars")
        if self._has_partitions(directory):
            return sorted(directory.rglob("*.parquet"))
        return [legacy] if legacy.exists() else []

    def daily_bar_summary(self) -> pd.DataFrame:
        """One row per symbol: how many bars, over which dates, and how many need attention.

        Columns: ``rows`` (all stored rows), ``unique_rows`` (distinct trade dates), ``start``,
        ``end``, ``unknown_status_rows`` (quality status other than OK) and
        ``missing_price_rows`` (no raw open or close). Indexed by symbol, sorted.

        Overview pages need these counts, not the prices. Only the five columns behind them are
        read, and the result is kept until a bar file changes (path, modification time or size),
        so a backfill or a single-stock update is picked up on the next call.
        """

        files = self._daily_bar_files()
        signature = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in files)
        key = str(self.root.resolve())
        with _SUMMARY_LOCK:
            cached = _SUMMARY_CACHE.get(key)
            if cached is None or cached[0] != signature:
                cached = (signature, _summarize_daily_bars(files))
                _SUMMARY_CACHE[key] = cached
            return cached[1].copy()

    def adj_factor_changes(self) -> pd.DataFrame:
        """Every day a stock's adjustment factor changed: ``symbol, trade_date, previous_date, ratio``.

        Reads three columns of the bars and is kept until a bar file changes, like the summary.
        """

        from quant_platform.data.corporate_action_gaps import factor_changes

        files = self._daily_bar_files()
        signature = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in files)
        key = "factors:" + str(self.root.resolve())
        with _SUMMARY_LOCK:
            cached = _SUMMARY_CACHE.get(key)
            if cached is None or cached[0] != signature:
                parts = []
                for path in files:
                    names = pq.read_schema(path).names
                    if {"symbol", "trade_date", "adj_factor"} <= set(names):
                        parts.append(pq.ParquetFile(path, read_dictionary=["symbol"]).read(
                            columns=["symbol", "trade_date", "adj_factor"]).to_pandas())
                bars = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["symbol", "trade_date", "adj_factor"])
                bars["symbol"] = bars["symbol"].astype(str)
                cached = (signature, factor_changes(bars.drop_duplicates(["symbol", "trade_date"], keep="last")))
                _SUMMARY_CACHE[key] = cached
            return cached[1].copy()

    def daily_bar_bounds(self) -> tuple[date, date] | None:
        """Read only the date column; never load prices just to bound a request."""
        directory, legacy = self._partition_path("daily_bars"), self._flat_path("daily_bars")
        source = directory if self._has_partitions(directory) else legacy
        if not source.exists():
            return None
        frame = pd.read_parquet(source, columns=["trade_date"])
        dates = pd.to_datetime(frame["trade_date"], errors="coerce").dropna()
        return (dates.min().date(), dates.max().date()) if not dates.empty else None

    def last_adjusted_bar_dates(
        self, symbols: list[str], *, before: date, since: date | None = None
    ) -> dict[str, date]:
        """Each symbol's latest bar with a valid adjustment factor in ``[since, before)``.

        Reads three columns, newest year first, and stops once every symbol is found.
        """

        directory, legacy = self._partition_path("daily_bars"), self._flat_path("daily_bars")
        if self._has_partitions(directory):
            years = sorted(
                (int(path.name.split("=", 1)[1]), path)
                for path in directory.glob(f"{_PARTITION_COLUMN}=*")
            )
            sources = [
                path
                for year, path in reversed(years)
                if year <= before.year and (since is None or year >= since.year)
            ]
        else:
            sources = [legacy] if legacy.exists() else []
        filters = [("trade_date", "<", pd.Timestamp(before))]
        if since is not None:
            filters.append(("trade_date", ">=", pd.Timestamp(since)))
        remaining = set(symbols)
        found: dict[str, date] = {}
        for source in sources:
            if not remaining:
                break
            try:
                frame = pd.read_parquet(
                    source,
                    columns=["symbol", "trade_date", "adj_factor"],
                    filters=[("symbol", "in", sorted(remaining)), *filters],
                )
            except (KeyError, ValueError):
                # A table saved without factors has no adjustment basis to preserve.
                continue
            frame = frame[pd.to_numeric(frame["adj_factor"], errors="coerce").gt(0)]
            latest = pd.to_datetime(frame["trade_date"]).groupby(frame["symbol"]).max()
            found.update({str(symbol): day.date() for symbol, day in latest.items()})
            remaining.difference_update(found)
        return found

    @staticmethod
    def _has_partitions(directory: Path) -> bool:
        return directory.exists() and any(directory.iterdir())

    @staticmethod
    def _drop_partition_column(frame: pd.DataFrame) -> pd.DataFrame:
        if _PARTITION_COLUMN in frame.columns:
            return frame.drop(columns=[_PARTITION_COLUMN])
        return frame

    @staticmethod
    def _dedupe(frame: pd.DataFrame, keys: list[str] | None) -> pd.DataFrame:
        if keys and all(key in frame.columns for key in keys):
            return frame.drop_duplicates(keys, keep="last").sort_values(keys).reset_index(drop=True)
        return frame


_SUMMARY_COLUMNS = ["rows", "unique_rows", "start", "end", "unknown_status_rows", "missing_price_rows"]
# 数据目录 -> (文件指纹, 汇总)。两个请求同时到达时，后一个等前一个算完后直接用结果。
_SUMMARY_CACHE: dict[str, tuple[tuple, pd.DataFrame]] = {}
_SUMMARY_LOCK = RLock()
# 给每只股票留出的日期编号范围（约 2700 年），用来把（股票，日期）合成一个整数。
_DAYS_PER_SYMBOL = 1_000_000


def _summarize_daily_bars(files: list[Path]) -> pd.DataFrame:
    """Aggregate the stored bars per symbol from the columns the counts depend on."""

    wanted = ["symbol", "trade_date", "quality_status", "raw_open", "raw_close"]
    parts: list[pd.DataFrame] = []
    spans: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for path in files:
        schema = pq.read_schema(path)
        columns = [column for column in wanted if column in schema.names]
        if not {"symbol", "trade_date"} <= set(columns):
            continue
        # 代码和状态重复度很高，按字典读取可以省掉上百万个字符串对象。
        texts = [name for name in ("symbol", "quality_status") if name in columns and pa.types.is_string(schema.field(name).type)]
        frame = pq.ParquetFile(path, read_dictionary=texts).read(columns=columns).to_pandas()
        frame = frame[frame["symbol"].notna()]
        if frame.empty:
            continue
        frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.normalize()
        parts.append(_summarize_file(frame))
        spans.append((frame["trade_date"].min(), frame["trade_date"].max()))
    if not parts:
        return pd.DataFrame(columns=_SUMMARY_COLUMNS, index=pd.Index([], name="symbol"))
    summary = pd.concat(parts).groupby(level=0, sort=True).agg(
        rows=("rows", "sum"),
        unique_rows=("unique_rows", "sum"),
        start=("start", "min"),
        end=("end", "max"),
        unknown_status_rows=("unknown_status_rows", "sum"),
        missing_price_rows=("missing_price_rows", "sum"),
    )
    ordered = sorted(span for span in spans if pd.notna(span[0]))
    if any(later[0] <= earlier[1] for earlier, later in zip(ordered, ordered[1:])):
        # 两个文件的日期有重叠时，同一个（股票，日期）可能各存了一份：按全部数据重新去重。
        pairs = pd.concat([pd.read_parquet(path, columns=["symbol", "trade_date"]) for path in files], ignore_index=True)
        pairs["trade_date"] = pd.to_datetime(pairs["trade_date"]).dt.normalize()
        distinct = pairs.drop_duplicates().groupby(pairs["symbol"].astype(str)).size()
        summary["unique_rows"] = distinct.reindex(summary.index).fillna(0)
    summary.index = summary.index.rename("symbol")
    return summary.astype({"rows": int, "unique_rows": int, "unknown_status_rows": int, "missing_price_rows": int})[_SUMMARY_COLUMNS]


def _summarize_file(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-symbol counts for the rows of one bar file (``trade_date`` already normalized)."""

    symbols = frame["symbol"].astype("category").cat.remove_unused_categories()
    # 与逐行统计的口径一致：没有状态列时都算正常；没有价格列时都算缺价格。
    unknown = ~(frame["quality_status"] == "OK") if "quality_status" in frame else pd.Series(False, index=frame.index)
    missing = pd.Series(False, index=frame.index)
    for column in ("raw_open", "raw_close"):
        missing |= frame[column].isna() if column in frame else True
    summary = pd.DataFrame({"date": frame["trade_date"], "unknown": unknown.astype(bool), "missing": missing}).groupby(
        symbols, sort=True, observed=True
    ).agg(
        rows=("date", "size"),
        start=("date", "min"),
        end=("date", "max"),
        unknown_status_rows=("unknown", "sum"),
        missing_price_rows=("missing", "sum"),
    )
    # 每只股票有多少个不同的交易日：把（股票，日期）合成一个整数。文件通常已经按股票、日期
    # 排好序，这时重复的行一定相邻，数一遍就够了；没排好序时才去重。
    codes = symbols.cat.codes.to_numpy("int64")
    pairs = codes * _DAYS_PER_SYMBOL + frame["trade_date"].to_numpy("datetime64[D]").astype("int64") % _DAYS_PER_SYMBOL
    if np.all(pairs[1:] >= pairs[:-1]):
        first = np.concatenate(([True], pairs[1:] != pairs[:-1]))
        distinct = np.bincount(codes[first], minlength=len(symbols.cat.categories))
    else:
        distinct = np.bincount(pd.unique(pairs) // _DAYS_PER_SYMBOL, minlength=len(symbols.cat.categories))
    summary["unique_rows"] = pd.Series(distinct, index=symbols.cat.categories).reindex(summary.index)
    summary.index = summary.index.astype(str)
    return summary
