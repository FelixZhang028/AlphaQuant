"""SQLite 行情缓存：避免重复网络请求，命中失败不影响主流程（显式降级）。"""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

from trading_agents.schemas import OHLCVBar
from trading_agents.utils import get_logger

log = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume INTEGER,
    PRIMARY KEY (symbol, date)
);
"""


class BarCache:
    """按 (symbol, date) 缓存 OHLCV。"""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def get(self, symbol: str, start: dt.date, end: dt.date) -> list[OHLCVBar]:
        rows = self._conn.execute(
            "SELECT date, open, high, low, close, volume FROM bars "
            "WHERE symbol=? AND date BETWEEN ? AND ? ORDER BY date",
            (symbol, start.isoformat(), end.isoformat()),
        ).fetchall()
        return [
            OHLCVBar(
                date=dt.date.fromisoformat(r[0]),
                open=r[1], high=r[2], low=r[3], close=r[4], volume=int(r[5]),
            )
            for r in rows
        ]

    def put(self, symbol: str, bars: list[OHLCVBar]) -> None:
        self._conn.executemany(
            "INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?,?)",
            [
                (symbol, b.date.isoformat(), b.open, b.high, b.low, b.close, b.volume)
                for b in bars
            ],
        )
        self._conn.commit()

    def covers(self, symbol: str, start: dt.date, end: dt.date) -> bool:
        """缓存是否已覆盖 [start, end] 区间（按是否有任一数据粗略判断）。"""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM bars WHERE symbol=? AND date BETWEEN ? AND ?",
            (symbol, start.isoformat(), end.isoformat()),
        ).fetchone()
        return bool(row and row[0] > 0)

    def close(self) -> None:
        self._conn.close()
