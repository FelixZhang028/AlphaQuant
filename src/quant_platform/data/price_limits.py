"""Auditable, conservative daily-price-limit derivation for Chinese equities."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import pandas as pd

PRICE_LIMIT_RULE_VERSION = "cn_daily_limit_v1"
_PRICE_TICK = Decimal("0.01")
_CHINEXT_REFORM = pd.Timestamp("2020-08-24")


def derive_cn_price_limits(frame: pd.DataFrame) -> pd.DataFrame:
    """Derive normal daily limits and leave unverifiable listing windows unknown.

    The input must contain symbol, trade_date, pre_close, is_st, and list_date.
    New-listing windows deliberately remain unknown because calendar days cannot
    safely stand in for the exchange's trading-day-specific exceptions.
    """

    required = {"symbol", "trade_date", "pre_close", "is_st", "list_date"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Price-limit derivation is missing columns: {missing}")

    result = frame.copy()
    derived = result.apply(_derive_row, axis=1, result_type="expand")
    derived.columns = ["up_limit", "down_limit", "limit_rule_id"]
    result[["up_limit", "down_limit", "limit_rule_id"]] = derived
    result["price_limit_source"] = "derived"
    result.loc[result["up_limit"].isna(), "price_limit_source"] = "unverified"
    return result


def _derive_row(row: pd.Series) -> tuple[float | None, float | None, str]:
    trade_date = pd.to_datetime(row["trade_date"], errors="coerce")
    list_date = pd.to_datetime(row["list_date"], errors="coerce")
    if pd.isna(trade_date):
        return None, None, "UNKNOWN_TRADE_DATE"
    if pd.isna(list_date):
        return None, None, "UNKNOWN_LIST_DATE"
    if trade_date < list_date:
        return None, None, "BEFORE_LISTING"
    if (trade_date - list_date).days <= 10:
        return None, None, "UNVERIFIED_NEW_LISTING_WINDOW"
    if pd.isna(row["is_st"]):
        return None, None, "UNKNOWN_ST_STATUS"

    try:
        pre_close = Decimal(str(row["pre_close"]))
    except (InvalidOperation, ValueError):
        return None, None, "UNKNOWN_PRE_CLOSE"
    if not pre_close.is_finite() or pre_close <= 0:
        return None, None, "UNKNOWN_PRE_CLOSE"

    code = str(row["symbol"]).split(".")[0].zfill(6)
    rate, rule = _rate_for(code, pd.Timestamp(trade_date), bool(row["is_st"]))
    rate_decimal = Decimal(str(rate))
    up = (pre_close * (Decimal("1") + rate_decimal)).quantize(
        _PRICE_TICK, rounding=ROUND_HALF_UP
    )
    down = (pre_close * (Decimal("1") - rate_decimal)).quantize(
        _PRICE_TICK, rounding=ROUND_HALF_UP
    )
    return float(up), float(down), f"{PRICE_LIMIT_RULE_VERSION}:{rule}"


def _rate_for(code: str, trade_date: pd.Timestamp, is_st: bool) -> tuple[float, str]:
    if code.startswith(("4", "8", "92")):
        return 0.30, "BEIJING_30"
    if code.startswith(("688", "689")):
        return 0.20, "STAR_20"
    if code.startswith(("300", "301")) and trade_date >= _CHINEXT_REFORM:
        return 0.20, "CHINEXT_20"
    if is_st:
        return 0.05, "MAIN_ST_5"
    return 0.10, "MAIN_10"
