"""Deterministic synthetic A-share data used for demos and end-to-end tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from quant_platform.data.repositories.parquet_repository import (
    ParquetMarketDataRepository,
)


def generate_sample_market_data(
    root: str | Path,
    symbols: list[str],
    start_date: date,
    end_date: date,
    seed: int = 42,
) -> ParquetMarketDataRepository:
    """Generate reproducible daily bars with enough variation for the momentum demo."""

    repository = ParquetMarketDataRepository(root)
    dates = pd.bdate_range(start_date, end_date)
    repository.save_table(
        "trade_calendar",
        pd.DataFrame({"cal_date": dates, "is_open": 1, "exchange": "SSE"}),
    )
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    for symbol_index, symbol in enumerate(symbols):
        base = 8.0 + symbol_index * 3.0
        drift = 0.00015 + symbol_index * 0.00008
        previous = base
        adj_factor = 1.0
        for trade_date in dates:
            overnight = rng.normal(drift, 0.006)
            intraday = rng.normal(drift, 0.012)
            raw_open = max(previous * (1.0 + overnight), 0.5)
            raw_close = max(raw_open * (1.0 + intraday), 0.5)
            raw_high = max(raw_open, raw_close) * (1.0 + abs(rng.normal(0.004, 0.002)))
            raw_low = min(raw_open, raw_close) * (1.0 - abs(rng.normal(0.004, 0.002)))
            volume = float(rng.integers(3_000_000, 15_000_000))
            amount = volume * (raw_open + raw_close) / 2.0
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "raw_open": raw_open,
                    "raw_high": raw_high,
                    "raw_low": raw_low,
                    "raw_close": raw_close,
                    "pre_close": previous,
                    "volume": volume,
                    "amount": amount,
                    "adj_factor": adj_factor,
                    "adjusted_close": raw_close * adj_factor,
                    "up_limit": previous * 1.10,
                    "down_limit": previous * 0.90,
                    "is_suspended": False,
                    "is_st": False,
                    "is_listed": True,
                    "source": "synthetic",
                    "ingested_at": pd.Timestamp.now(tz="UTC"),
                    "quality_status": "OK",
                }
            )
            previous = raw_close
    repository.save_table("daily_bars", pd.DataFrame(rows))
    repository.save_table(
        "security_master",
        pd.DataFrame(
            {
                "symbol": symbols,
                "name": [f"示例股票{i + 1}" for i in range(len(symbols))],
                "exchange": [symbol.split(".")[-1] for symbol in symbols],
                "list_status": "L",
                "list_date": pd.Timestamp("2000-01-01"),
            }
        ),
    )
    return repository
