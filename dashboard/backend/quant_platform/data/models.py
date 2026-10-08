"""Canonical market-data models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class DataQualityStatus(StrEnum):
    """Quality state assigned to a standardized market-data row."""

    OK = "OK"
    MISSING_PRICE = "MISSING_PRICE"
    MISSING_ADJ_FACTOR = "MISSING_ADJ_FACTOR"
    UNKNOWN_STATUS = "UNKNOWN_STATUS"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"


@dataclass(frozen=True)
class DailyBar:
    """Canonical daily bar; prices are raw unless explicitly adjusted."""

    symbol: str
    trade_date: date
    raw_open: float
    raw_high: float
    raw_low: float
    raw_close: float
    pre_close: float
    volume: float
    amount: float
    adj_factor: float
    adjusted_close: float
    up_limit: float | None
    down_limit: float | None
    is_suspended: bool
    is_st: bool
    is_listed: bool
    source: str
    ingested_at: datetime
    quality_status: DataQualityStatus
