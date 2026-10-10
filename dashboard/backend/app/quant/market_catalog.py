"""Small, file-versioned index for browsing local bars without loading prices."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from functools import lru_cache
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from .symbols import to_bare, to_canonical

_INDEX_LOCK = RLock()
_CACHE_VERSION = 1


def _cached_index(root: Path, signature: tuple):
    try:
        cached = json.loads((root / ".market-catalog.json").read_text(encoding="utf-8"))
        if cached["version"] != _CACHE_VERSION or tuple(tuple(item) for item in cached["signature"]) != signature:
            return None
        stats = cached["stats"]
        for stat in stats.values():
            stat["start"], stat["end"] = pd.Timestamp(stat["start"]), pd.Timestamp(stat["end"])
        return stats, [pd.Timestamp(day) for day in cached["sessions"]], cached["names"], tuple(cached["paths"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _save_index(root: Path, signature: tuple, result: tuple) -> None:
    stats, sessions, names, paths = result
    payload = {"version": _CACHE_VERSION, "signature": signature, "stats": {
        symbol: {**stat, "start": stat["start"].isoformat(), "end": stat["end"].isoformat()}
        for symbol, stat in stats.items()
    }, "sessions": [day.isoformat() for day in sessions], "names": names, "paths": paths}
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=root, prefix=".market-catalog-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False)
        os.replace(temporary, root / ".market-catalog.json")
    except OSError:
        # Browsing still works on a read-only repository; only persistence is skipped.
        pass
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _sources(root: Path) -> list[Path]:
    partitions = sorted((root / "daily_bars").rglob("*.parquet"))
    legacy = root / "daily_bars.parquet"
    return partitions or ([legacy] if legacy.exists() else [])


def _signature(root: Path) -> tuple[tuple[str, int, int], ...]:
    files = _sources(root) + [root / name for name in (
        "security_master.parquet", "trade_calendar.parquet"
    ) if (root / name).exists()]
    return tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in files)


def _read_columns(path: Path, wanted: list[str]) -> pd.DataFrame:
    parquet = pq.ParquetFile(path)
    columns = [column for column in wanted if column in parquet.schema_arrow.names]
    return parquet.read(columns=columns).to_pandas()


def _calendar(root: Path) -> list:
    path = root / "trade_calendar.parquet"
    if not path.exists():
        return []
    frame = _read_columns(path, ["cal_date", "is_open"])
    if "cal_date" not in frame:
        return []
    if "is_open" in frame:
        frame = frame[pd.to_numeric(frame["is_open"], errors="coerce").eq(1)]
    return sorted(set(pd.to_datetime(frame["cal_date"], errors="coerce").dropna().dt.normalize()))


@lru_cache(maxsize=4)
def _index(root: str, signature: tuple) -> tuple[dict, list, dict, tuple[str, ...]]:
    # The signature is part of the key: a backfill or a single-stock update invalidates it.
    cached = _cached_index(Path(root), signature)
    if cached is not None:
        return cached
    stats: dict[str, dict[str, Any]] = {}
    sessions = _calendar(Path(root))
    for path in _sources(Path(root)):
        frame = _read_columns(path, ["symbol", "trade_date", "quality_status"])
        if frame.empty:
            continue
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.normalize()
        frame = frame.dropna(subset=["symbol", "trade_date"])
        frame["symbol"] = frame["symbol"].astype(str).map(to_canonical)
        frame["unknown"] = frame["quality_status"].ne("OK") if "quality_status" in frame else True
        frame["session_date"] = frame["trade_date"].where(frame["trade_date"].isin(sessions))
        frame["unexpected"] = frame["session_date"].isna() if sessions else False
        grouped = frame.groupby("symbol").agg(
            rows=("trade_date", "size"), unique_rows=("trade_date", "nunique"),
            start=("trade_date", "min"), end=("trade_date", "max"),
            unknown=("unknown", "sum"),
            session_rows=("session_date", "nunique"), unexpected=("unexpected", "sum"),
        )
        for symbol, row in grouped.iterrows():
            previous = stats.get(symbol)
            stats[symbol] = {
                "rows": int(row["rows"]) + (previous["rows"] if previous else 0),
                "unique_rows": int(row["unique_rows"]) + (previous["unique_rows"] if previous else 0),
                "start": min(row["start"], previous["start"]) if previous else row["start"],
                "end": max(row["end"], previous["end"]) if previous else row["end"],
                "unknown": int(row["unknown"]) + (previous["unknown"] if previous else 0),
                "session_rows": int(row["session_rows"]) + (previous["session_rows"] if previous else 0),
                "unexpected": int(row["unexpected"]) + (previous["unexpected"] if previous else 0),
            }
    names = {}
    master = Path(root) / "security_master.parquet"
    if master.exists():
        frame = _read_columns(master, ["symbol", "name"])
        if {"symbol", "name"}.issubset(frame.columns):
            names = {to_canonical(str(row.symbol)): str(row.name) for row in frame.itertuples()
                     if pd.notna(row.symbol) and pd.notna(row.name)}
    for stat in stats.values():
        start, end = stat["start"], stat["end"]
        calendar_covers = bool(sessions and sessions[0] <= start and sessions[-1] >= end)
        expected = bisect_right(sessions, end) - bisect_left(sessions, start) if calendar_covers else None
        stat["expected_rows"] = expected
        stat["missing_rows"] = max(expected - stat["session_rows"], 0) if expected is not None else None
        stat["coverage"] = min(stat["session_rows"] / expected, 1.0) if expected else None
    result = stats, sessions, names, tuple(str(path) for path in _sources(Path(root)))
    if _signature(Path(root)) != signature:
        raise RuntimeError("行情正在更新，请稍后刷新列表")
    _save_index(Path(root), signature, result)
    return result


class LocalMarketCatalog:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        with _INDEX_LOCK:
            self.stats, self.sessions, self.names, self.paths = _index(str(self.root), _signature(self.root))

    def _row(self, symbol: str, universe: set[str]) -> dict:
        stat = self.stats.get(symbol)
        if not stat:
            return {"symbol": to_bare(symbol), "name": self.names.get(symbol, "名称待补充"),
                    "in_universe": symbol in universe, "start_date": None, "end_date": None,
                    "rows": 0, "coverage": None, "missing_rows": None, "unknown_rows": 0,
                    "duplicate_rows": 0, "unexpected_rows": 0, "status": "NO_DATA", "status_label": "未下载行情"}
        duplicates = stat["rows"] - stat["unique_rows"]
        state = "CHECK" if stat["unknown"] or duplicates or stat["unexpected"] or stat["coverage"] is None else (
            "GAPS" if stat["missing_rows"] else "COMPLETE")
        return {"symbol": to_bare(symbol), "name": self.names.get(symbol, "名称待补充"),
                "in_universe": symbol in universe, "start_date": stat["start"].date().isoformat(),
                "end_date": stat["end"].date().isoformat(), "rows": stat["rows"],
                "coverage": stat["coverage"], "missing_rows": stat["missing_rows"],
                "unknown_rows": stat["unknown"], "duplicate_rows": duplicates, "unexpected_rows": stat["unexpected"],
                "status": state, "status_label": {"CHECK": "待核对", "GAPS": "区间有缺失",
                                                       "COMPLETE": "已保存区间完整"}[state]}

    def page(self, universe: list[str], *, scope: str = "all", q: str = "", page: int = 1,
             page_size: int = 20) -> dict:
        pool = {to_canonical(symbol) for symbol in universe}
        symbols = sorted(pool if scope == "universe" else self.stats)
        query = q.strip().casefold()
        matched = [symbol for symbol in symbols if not query or query in symbol.casefold()
                   or query in self.names.get(symbol, "名称待补充").casefold()]
        pages = max(1, (len(matched) + page_size - 1) // page_size)
        page = min(page, pages)
        selected = matched[(page - 1) * page_size:page * page_size]
        return {"items": [self._row(symbol, pool) for symbol in selected], "total": len(matched),
                "page": page, "page_size": page_size, "pages": pages,
                "downloaded_count": len(self.stats), "universe_count": len(pool),
                "universe_downloaded_count": len(pool.intersection(self.stats))}

    def detail(self, symbol: str, universe: list[str]) -> dict:
        canonical = to_canonical(symbol)
        pool = {to_canonical(item) for item in universe}
        if canonical not in self.stats and canonical not in pool:
            raise KeyError(symbol)
        row = self._row(canonical, pool)
        present = set()
        for filename in self.paths if row["rows"] else ():
            # Predicate pushdown and one column; the price table never enters Python here.
            frame = pd.read_parquet(filename, columns=["trade_date"], filters=[("symbol", "==", canonical)])
            present.update(pd.to_datetime(frame["trade_date"], errors="coerce").dropna().dt.normalize())
        missing_ranges = []
        if row["coverage"] is not None:
            start, end = pd.Timestamp(row["start_date"]), pd.Timestamp(row["end_date"])
            relevant = self.sessions[bisect_left(self.sessions, start):bisect_right(self.sessions, end)]
            current = None
            for session in relevant:
                if session in present:
                    current = None
                elif current is None:
                    current = {"start_date": session.date().isoformat(), "end_date": session.date().isoformat(), "days": 1}
                    missing_ranges.append(current)
                else:
                    current["end_date"] = session.date().isoformat()
                    current["days"] += 1
            row["missing_rows"] = sum(item["days"] for item in missing_ranges)
            row["coverage"] = (len(relevant) - row["missing_rows"]) / len(relevant) if relevant else None
            if row["status"] != "CHECK":
                row["status"] = "GAPS" if missing_ranges else "COMPLETE"
                row["status_label"] = "区间有缺失" if missing_ranges else "已保存区间完整"
        return {**row, "missing_ranges": missing_ranges[:20], "missing_range_count": len(missing_ranges)}
