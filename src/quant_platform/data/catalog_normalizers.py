"""Normalize AkShare security-master and benchmark datasets."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from quant_platform.core.exceptions import DataQualityError
from quant_platform.data.normalizers import canonical_symbol


def _require_columns(frame: pd.DataFrame, columns: set[str], source: str) -> None:
    missing = sorted(columns.difference(frame.columns))
    if missing:
        raise DataQualityError(f"{source} data is missing columns: {missing}")


def normalize_akshare_security_master(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize AkShare's current沪深京 A-share list."""

    result = frame.rename(
        columns={"code": "symbol", "name": "name", "代码": "symbol", "名称": "name"}
    ).copy()
    _require_columns(result, {"symbol", "name"}, "akshare.stock_info_a_code_name")
    result["symbol"] = result["symbol"].astype(str).str.zfill(6).map(canonical_symbol)
    result["exchange"] = result["symbol"].str.rsplit(".", n=1).str[-1]
    result["list_status"] = "L"
    result["list_date"] = pd.NaT
    result["delist_date"] = pd.NaT
    result["source"] = "akshare"
    result["ingested_at"] = datetime.now(UTC)
    return result[
        [
            "symbol",
            "name",
            "exchange",
            "list_status",
            "list_date",
            "delist_date",
            "source",
            "ingested_at",
        ]
    ].drop_duplicates("symbol", keep="last")


def normalize_akshare_index_daily(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Normalize AkShare ``index_zh_a_hist`` daily output."""

    aliases = {
        "日期": "trade_date",
        "开盘": "raw_open",
        "最高": "raw_high",
        "最低": "raw_low",
        "收盘": "raw_close",
        "成交量": "volume",
        "成交额": "amount",
    }
    result = frame.rename(columns=aliases).copy()
    _require_columns(
        result,
        {"trade_date", "raw_open", "raw_high", "raw_low", "raw_close"},
        "akshare.index_zh_a_hist",
    )
    result["symbol"] = symbol
    result["trade_date"] = pd.to_datetime(result["trade_date"]).dt.normalize()
    result = result.sort_values("trade_date")
    result["pre_close"] = result["raw_close"].shift(1)
    result["volume"] = pd.to_numeric(
        result.get("volume", pd.Series(index=result.index, dtype=float)),
        errors="coerce",
    )
    result["amount"] = pd.to_numeric(
        result.get("amount", pd.Series(index=result.index, dtype=float)),
        errors="coerce",
    )
    for field in ("raw_open", "raw_high", "raw_low", "raw_close"):
        result[field] = pd.to_numeric(result[field], errors="coerce")
    result["source"] = "akshare"
    result["ingested_at"] = datetime.now(UTC)
    result["quality_status"] = "OK"
    result.loc[result[["raw_open", "raw_close"]].isna().any(axis=1), "quality_status"] = (
        "MISSING_PRICE"
    )
    columns = [
        "symbol",
        "trade_date",
        "raw_open",
        "raw_high",
        "raw_low",
        "raw_close",
        "pre_close",
        "volume",
        "amount",
        "source",
        "ingested_at",
        "quality_status",
    ]
    return result[columns].reset_index(drop=True)
