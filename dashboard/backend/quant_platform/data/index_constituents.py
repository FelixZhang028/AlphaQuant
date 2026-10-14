"""Index constituents over time, stored as the full member list at each date it changed.

The vendor answers "which stocks were in the index on day D"; its lists are refreshed once a
week (every Monday). A list is stored for the first date checked and for every date on which it
differs from the one before, so a table holds a few dozen lists per index. ``membership`` turns
them into the dated intervals a historical universe needs: a stock is a member from the date it
first appears in a list until the date of the first list without it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd

from quant_platform.data.normalizers import canonical_symbol

CONSTITUENTS_TABLE = "index_constituents"
CHECKS_TABLE = "index_constituent_checks"
# 可以用作历史股票池的指数：代码 -> (名称, 厂商接口里的名字)。
INDEX_UNIVERSES: dict[str, tuple[str, str]] = {
    "000300.SH": ("沪深300", "hs300"),
    "000016.SH": ("上证50", "sz50"),
    "000905.SH": ("中证500", "zz500"),
}
COLUMNS = ["index_symbol", "effective_date", "symbol", "source", "ingested_at"]
MEMBERSHIP_COLUMNS = ["symbol", "effective_from", "effective_to", "known_at", "source"]
# 成分股半年调整一次。核对日期比回测结束日早这么多天以内，仍然认为是最新的。
MAX_DAYS_SINCE_CHECK = 31


def index_name(index_symbol: str) -> str:
    return INDEX_UNIVERSES[index_symbol][0]


def week_start(day: date) -> date:
    """The Monday of the week ``day`` is in: the date of the vendor's list in force that day."""

    return day - timedelta(days=day.weekday())


def normalize_baostock_constituents(frame: pd.DataFrame, index_symbol: str, effective_date: date) -> pd.DataFrame:
    """A vendor list -> one row per member, dated ``effective_date`` (the Monday that was asked for)."""

    if frame.empty or "code" not in frame.columns:
        return pd.DataFrame(columns=COLUMNS)
    result = pd.DataFrame({
        "index_symbol": index_symbol,
        "effective_date": pd.Timestamp(effective_date),
        "symbol": frame["code"].astype(str).map(canonical_symbol),
        "source": "baostock",
        "ingested_at": datetime.now(UTC),
    })
    return result.drop_duplicates("symbol").sort_values("symbol").reset_index(drop=True)


def stored_lists(constituents: pd.DataFrame, index_symbol: str) -> dict[date, frozenset[str]]:
    """The stored member lists of one index, by date."""

    if constituents.empty or not {"index_symbol", "effective_date", "symbol"} <= set(constituents.columns):
        return {}
    rows = constituents[constituents["index_symbol"] == index_symbol]
    days = pd.to_datetime(rows["effective_date"]).dt.date
    return {day: frozenset(group.astype(str)) for day, group in rows["symbol"].groupby(days)}


def members_on(lists: dict[date, frozenset[str]], day: date) -> frozenset[str] | None:
    """The list in force on ``day``: the newest stored one dated on or before it."""

    earlier = [stored for stored in lists if stored <= day]
    return lists[max(earlier)] if earlier else None


def membership(constituents: pd.DataFrame, index_symbol: str) -> pd.DataFrame:
    """Dated intervals for a historical universe: one row per unbroken stay of a stock in the index.

    ``effective_to`` is the date of the first list without the stock (missing while it is still a
    member). Changes are announced about two weeks before they take effect, so a stay is known
    from its first day.
    """

    lists = stored_lists(constituents, index_symbol)
    rows: list[dict[str, object]] = []
    since: dict[str, date] = {}
    for day in sorted(lists):
        current = lists[day]
        for symbol in [symbol for symbol in since if symbol not in current]:
            rows.append({"symbol": symbol, "effective_from": since.pop(symbol), "effective_to": day})
        for symbol in current:
            since.setdefault(symbol, day)
    rows.extend({"symbol": symbol, "effective_from": start, "effective_to": None} for symbol, start in since.items())
    result = pd.DataFrame(rows, columns=["symbol", "effective_from", "effective_to"])
    for column in ("effective_from", "effective_to"):
        result[column] = pd.to_datetime(result[column])
    result["known_at"] = result["effective_from"]
    result["source"] = f"index:{index_symbol}"
    return result[MEMBERSHIP_COLUMNS].sort_values(["symbol", "effective_from"]).reset_index(drop=True)


def checked_range(checks: pd.DataFrame, index_symbol: str) -> tuple[date, date] | None:
    """The dates between which the member lists of an index have been checked, or None."""

    if checks.empty or "index_symbol" not in checks.columns:
        return None
    rows = checks[checks["index_symbol"] == index_symbol]
    if rows.empty or rows[["checked_from", "checked_through"]].isna().any().any():
        return None
    row = rows.iloc[-1]
    return pd.Timestamp(row["checked_from"]).date(), pd.Timestamp(row["checked_through"]).date()


def require_coverage(checks: pd.DataFrame, index_symbol: str, start_date: date, end_date: date) -> None:
    """Refuse a backtest whose dates the stored member lists do not cover."""

    name = index_name(index_symbol)
    covered = checked_range(checks, index_symbol)
    if covered is None:
        raise ValueError(f"本地还没有{name}的历史成分股，请先在「数据更新」里下载。")
    first, last = covered
    if start_date < first:
        raise ValueError(
            f"{name}的历史成分股从 {first} 开始，早于这一天不知道当时有哪些成分股。请把开始日期改到 {first} 或之后。"
        )
    if end_date > last + timedelta(days=MAX_DAYS_SINCE_CHECK):
        raise ValueError(f"{name}的成分股只核对到 {last}，请先在「数据更新」里更新指数成分股。")
