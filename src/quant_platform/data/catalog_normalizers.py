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


def normalize_akshare_corporate_actions(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Normalize AkShare ``stock_fhps_detail_em`` entitlements for one symbol.

    接口口径：现金分红与送转比例均按"每 10 股"计；仅保留已实施方案
    （``方案进度`` 含"实施"）且有除权除息日的记录；同一除权日的多次
    分配合并为一条（回测引擎按 symbol+ex_date 唯一消费）。
    """

    columns = ["symbol", "ex_date", "cash_per_share", "share_multiplier"]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    _require_columns(
        frame,
        {"除权除息日", "方案进度", "现金分红-现金分红比例"},
        "akshare.stock_fhps_detail_em",
    )
    result = frame.copy()
    result["ex_date"] = pd.to_datetime(result["除权除息日"], errors="coerce")
    result = result[
        result["ex_date"].notna()
        & result["方案进度"].astype(str).str.contains("实施", na=False)
    ]
    if result.empty:
        return pd.DataFrame(columns=columns)
    cash_per_ten = pd.to_numeric(
        result["现金分红-现金分红比例"], errors="coerce"
    ).fillna(0.0)
    bonus_columns = ("送转股份-送股比例", "送转股份-转股比例")
    if all(column in result.columns for column in bonus_columns):
        bonus_per_ten = sum(
            pd.to_numeric(result[column], errors="coerce").fillna(0.0)
            for column in bonus_columns
        )
    elif "送转股份-送转总比例" in result.columns:
        bonus_per_ten = pd.to_numeric(
            result["送转股份-送转总比例"], errors="coerce"
        ).fillna(0.0)
    else:
        bonus_per_ten = pd.Series(0.0, index=result.index)
    normalized = pd.DataFrame(
        {
            "symbol": str(symbol),
            "ex_date": result["ex_date"].dt.normalize(),
            "cash_per_share": cash_per_ten / 10.0,
            "share_multiplier": 1.0 + bonus_per_ten / 10.0,
        }
    )
    aggregated = (
        normalized.groupby("ex_date", as_index=False)
        .agg(
            cash_per_share=("cash_per_share", "sum"),
            share_multiplier=("share_multiplier", "prod"),
        )
    )
    aggregated["symbol"] = str(symbol)
    # 既无现金也无送转的记录对结算没有意义，直接剔除。
    meaningful = (aggregated["cash_per_share"] > 0) | (
        aggregated["share_multiplier"] != 1.0
    )
    return aggregated.loc[meaningful, columns].sort_values("ex_date").reset_index(drop=True)


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
