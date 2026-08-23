"""Normalize provider-specific fields and units into canonical columns."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from quant_platform.core.exceptions import DataQualityError

CANONICAL_BAR_COLUMNS = [
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
]


def _require_columns(frame: pd.DataFrame, columns: set[str], source: str) -> None:
    missing = sorted(columns.difference(frame.columns))
    if missing:
        raise DataQualityError(f"{source} data is missing columns: {missing}")


def normalize_tushare_daily(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize Tushare ``daily`` output; volume becomes shares and amount yuan."""

    _require_columns(
        frame,
        {
            "ts_code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "vol",
            "amount",
        },
        "tushare.daily",
    )
    result = frame.rename(
        columns={
            "ts_code": "symbol",
            "open": "raw_open",
            "high": "raw_high",
            "low": "raw_low",
            "close": "raw_close",
            "vol": "volume",
        }
    ).copy()
    result["trade_date"] = pd.to_datetime(result["trade_date"]).dt.normalize()
    result["volume"] = pd.to_numeric(result["volume"], errors="coerce") * 100.0
    result["amount"] = pd.to_numeric(result["amount"], errors="coerce") * 1000.0
    result["source"] = "tushare"
    result["ingested_at"] = datetime.now(UTC)
    return result[CANONICAL_BAR_COLUMNS]


def normalize_akshare_daily(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize AkShare ``stock_zh_a_hist`` output."""

    aliases = {
        "日期": "trade_date",
        "股票代码": "symbol",
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
        {
            "symbol",
            "trade_date",
            "raw_open",
            "raw_high",
            "raw_low",
            "raw_close",
            "volume",
            "amount",
        },
        "akshare.stock_zh_a_hist",
    )
    result["symbol"] = result["symbol"].astype(str).str.zfill(6).map(canonical_symbol)
    result["trade_date"] = pd.to_datetime(result["trade_date"]).dt.normalize()
    result = result.sort_values(["symbol", "trade_date"])
    result["pre_close"] = result.groupby("symbol", observed=True)["raw_close"].shift(1)
    # Current stock_zh_a_hist documentation defines volume in lots and amount in yuan.
    result["volume"] = pd.to_numeric(result["volume"], errors="coerce") * 100.0
    result["amount"] = pd.to_numeric(result["amount"], errors="coerce")
    result["source"] = "akshare"
    result["ingested_at"] = datetime.now(UTC)
    return result[CANONICAL_BAR_COLUMNS]


def normalize_ifind_daily(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize official iFinD ``THS_HQ`` daily-history output."""

    aliases = {
        "thscode": "symbol",
        "code": "symbol",
        "time": "trade_date",
        "date": "trade_date",
        "open": "raw_open",
        "high": "raw_high",
        "low": "raw_low",
        "close": "raw_close",
        "preclose": "pre_close",
        "pre_close": "pre_close",
        "volume": "volume",
        "amount": "amount",
    }
    renamed = {column: aliases.get(str(column).lower(), column) for column in frame.columns}
    result = frame.rename(columns=renamed).copy()
    _require_columns(
        result,
        {
            "symbol",
            "trade_date",
            "raw_open",
            "raw_high",
            "raw_low",
            "raw_close",
            "volume",
            "amount",
        },
        "ifind.THS_HQ",
    )
    result["symbol"] = result["symbol"].astype(str).map(canonical_symbol)
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce").dt.normalize()
    result = result.sort_values(["symbol", "trade_date"])
    if "pre_close" not in result.columns:
        result["pre_close"] = result.groupby("symbol", observed=True)["raw_close"].shift(1)
    numeric_columns = [
        "raw_open",
        "raw_high",
        "raw_low",
        "raw_close",
        "pre_close",
        "volume",
        "amount",
    ]
    for column in numeric_columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result["source"] = "ifind"
    result["ingested_at"] = datetime.now(UTC)
    return result[CANONICAL_BAR_COLUMNS]


def normalize_baostock_daily(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize BaoStock history while preserving its execution-status fields."""

    _require_columns(
        frame,
        {
            "date",
            "code",
            "open",
            "high",
            "low",
            "close",
            "preclose",
            "volume",
            "amount",
            "tradestatus",
            "isST",
        },
        "baostock.query_history_k_data_plus",
    )
    result = frame.rename(
        columns={
            "date": "trade_date",
            "code": "symbol",
            "open": "raw_open",
            "high": "raw_high",
            "low": "raw_low",
            "close": "raw_close",
            "preclose": "pre_close",
        }
    ).copy()
    result["symbol"] = result["symbol"].astype(str).map(canonical_symbol)
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce").dt.normalize()
    for column in (
        "raw_open",
        "raw_high",
        "raw_low",
        "raw_close",
        "pre_close",
        "volume",
        "amount",
    ):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result["source"] = "baostock"
    result["ingested_at"] = datetime.now(UTC)
    status = result["tradestatus"].astype("string").str.strip()
    st_status = result["isST"].astype("string").str.strip()
    result["is_suspended"] = status.map({"0": True, "1": False}).astype("boolean")
    result["is_st"] = st_status.map({"0": False, "1": True}).astype("boolean")
    result["status_known"] = status.isin(["0", "1"]) & st_status.isin(["0", "1"])
    return result[CANONICAL_BAR_COLUMNS + ["is_suspended", "is_st", "status_known"]]


def normalize_pytdx_daily(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Normalize PyTDX unadjusted daily bars; stock volume becomes shares."""

    aliases = {
        "datetime": "trade_date",
        "date": "trade_date",
        "open": "raw_open",
        "high": "raw_high",
        "low": "raw_low",
        "close": "raw_close",
        "vol": "volume",
    }
    result = frame.rename(columns=aliases).copy()
    if "trade_date" not in result.columns and {"year", "month", "day"}.issubset(result.columns):
        result["trade_date"] = pd.to_datetime(
            result[["year", "month", "day"]], errors="coerce"
        )
    _require_columns(
        result,
        {
            "trade_date",
            "raw_open",
            "raw_high",
            "raw_low",
            "raw_close",
            "volume",
            "amount",
        },
        "pytdx.get_security_bars",
    )
    result["symbol"] = canonical_symbol(symbol)
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce").dt.normalize()
    result = result.sort_values(["symbol", "trade_date"])
    for column in ("raw_open", "raw_high", "raw_low", "raw_close", "volume", "amount"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    # TDX stock daily bars report volume in lots; canonical volume uses shares.
    result["volume"] = result["volume"] * 100.0
    result["pre_close"] = result.groupby("symbol", observed=True)["raw_close"].shift(1)
    result["source"] = "pytdx"
    result["ingested_at"] = datetime.now(UTC)
    return result[CANONICAL_BAR_COLUMNS]


def canonical_symbol(code: str) -> str:
    """Convert a six-digit A-share code into ``000001.SZ`` style."""

    value = str(code).strip().lower()
    parts = value.split(".")
    if len(parts) == 2 and parts[0] in {"sh", "sz", "bj"}:
        clean = parts[1]
    else:
        clean = parts[0]
    clean = clean.removeprefix("sh").removeprefix("sz").removeprefix("bj")
    clean = clean.zfill(6)
    if clean.startswith(("4", "8", "9")):
        exchange = "BJ"
    elif clean.startswith(("5", "6", "9")):
        exchange = "SH"
    else:
        exchange = "SZ"
    return f"{clean}.{exchange}"


def normalize_suspensions(frame: pd.DataFrame, source: str) -> pd.DataFrame:
    """Normalize suspension output to canonical symbol and trade-date columns."""

    if frame.empty:
        return pd.DataFrame(columns=["symbol", "trade_date"])
    if source == "tushare":
        result = frame.rename(columns={"ts_code": "symbol"}).copy()
    else:
        result = frame.rename(
            columns={"代码": "symbol", "停牌时间": "trade_date", "日期": "trade_date"}
        ).copy()
        if "symbol" in result.columns:
            result["symbol"] = result["symbol"].astype(str).map(canonical_symbol)
    _require_columns(result, {"symbol"}, f"{source}.suspensions")
    return result


def compose_standard_daily(
    bars: pd.DataFrame,
    adjustment_factors: pd.DataFrame,
    price_limits: pd.DataFrame,
    suspensions: pd.DataFrame,
) -> pd.DataFrame:
    """Join daily source tables and assign deterministic quality states."""

    result = bars.copy()
    keys = ["symbol", "trade_date"]

    adj = adjustment_factors.rename(columns={"ts_code": "symbol"}).copy()
    if not adj.empty:
        adj["trade_date"] = pd.to_datetime(adj["trade_date"]).dt.normalize()
        result = result.merge(adj[keys + ["adj_factor"]], on=keys, how="left")
    else:
        result["adj_factor"] = pd.NA

    limits = price_limits.rename(
        columns={
            "ts_code": "symbol",
            "up_limit": "up_limit",
            "down_limit": "down_limit",
        }
    ).copy()
    if not limits.empty:
        limits["trade_date"] = pd.to_datetime(limits["trade_date"]).dt.normalize()
        result = result.merge(limits[keys + ["up_limit", "down_limit"]], on=keys, how="left")
    else:
        result["up_limit"] = pd.NA
        result["down_limit"] = pd.NA

    suspended_symbols: set[str] = set()
    if not suspensions.empty:
        suspended_symbols = set(suspensions["symbol"].astype(str))
    result["is_suspended"] = result["symbol"].isin(suspended_symbols)
    result["is_st"] = False
    result["is_listed"] = True
    result["adjusted_close"] = result["raw_close"] * pd.to_numeric(
        result["adj_factor"], errors="coerce"
    )
    result["quality_status"] = "OK"
    missing_price = result[["raw_open", "raw_close"]].isna().any(axis=1)
    missing_adj = result["adj_factor"].isna()
    unknown_status = result[["up_limit", "down_limit"]].isna().any(axis=1)
    result.loc[missing_price, "quality_status"] = "MISSING_PRICE"
    result.loc[~missing_price & missing_adj, "quality_status"] = "MISSING_ADJ_FACTOR"
    result.loc[~missing_price & ~missing_adj & unknown_status, "quality_status"] = "UNKNOWN_STATUS"
    return result.sort_values(keys).reset_index(drop=True)
