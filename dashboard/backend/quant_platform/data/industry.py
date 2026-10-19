"""Industry classification over time, stored as change points in ``security_exposures``.

The vendor answers "what was every stock's industry on day D" (CSRC classification: a sector
letter and a two-digit division, e.g. ``J66货币金融服务``). Snapshots are taken at quarter ends
and only the rows where a stock's industry differs from its previous known one are kept, so the
table stays a few thousand rows. A row says: from ``date`` on, this was the stock's industry.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from quant_platform.data.normalizers import canonical_symbol

EXPOSURES_TABLE = "security_exposures"
SNAPSHOTS_TABLE = "industry_snapshots"
MISSING_INDUSTRY_MESSAGE = "平台还没有行业分类，管理员更新后就能用。"
# 证监会行业分类的门类（第一位字母）。
SECTOR_NAMES = {
    "A": "农、林、牧、渔业", "B": "采矿业", "C": "制造业", "D": "电力、热力、燃气及水生产和供应业", "E": "建筑业",
    "F": "批发和零售业", "G": "交通运输、仓储和邮政业", "H": "住宿和餐饮业", "I": "信息传输、软件和信息技术服务业",
    "J": "金融业", "K": "房地产业", "L": "租赁和商务服务业", "M": "科学研究和技术服务业", "N": "水利、环境和公共设施管理业",
    "O": "居民服务、修理和其他服务业", "P": "教育", "Q": "卫生和社会工作", "R": "文化、体育和娱乐业", "S": "综合",
}
COLUMNS = ["symbol", "date", "industry", "sector", "source", "ingested_at"]
# 可以接到每根日线上的两列：当天的大类（如 ``J66货币金融服务``）和门类（如 ``J``）。
INDUSTRY_COLUMNS = ("industry", "sector")


def industry_columns(fields) -> list[str]:
    """The industry columns among the fields a factor or strategy asks for."""

    wanted = set(fields)
    return [column for column in INDUSTRY_COLUMNS if column in wanted]


def normalize_baostock_industry(frame: pd.DataFrame) -> pd.DataFrame:
    """A vendor snapshot -> (symbol, date, industry, sector) rows; stocks without a classification are left out.

    ``date`` is the day the vendor says the snapshot was current (its ``updateDate``), not the
    day that was asked for, so a classification is never dated earlier than it was known.
    """

    if frame.empty or not {"updateDate", "code", "industry"} <= set(frame.columns):
        return pd.DataFrame(columns=COLUMNS)
    industry = frame["industry"].astype(str).str.strip()
    result = pd.DataFrame({
        "symbol": frame["code"].astype(str).map(canonical_symbol),
        "date": pd.to_datetime(frame["updateDate"], errors="coerce").dt.normalize(),
        "industry": industry,
        "sector": industry.str[:1],
        "source": "baostock",
        "ingested_at": datetime.now(UTC),
    })
    # 退市等没有分类的股票，厂商给的是空串：不是一个行业，不保存。
    known = result["industry"].ne("") & result["sector"].isin(list(SECTOR_NAMES)) & result["date"].notna()
    return result[known].drop_duplicates("symbol", keep="last").reset_index(drop=True)


def new_change_points(existing: pd.DataFrame, snapshot: pd.DataFrame) -> pd.DataFrame:
    """The snapshot rows worth storing: a stock's first classification, or one that differs from
    the classification in force just before the snapshot's date."""

    if snapshot.empty:
        return snapshot
    if existing.empty or "industry" not in existing.columns:
        return snapshot
    known = existing.dropna(subset=["industry"])[["symbol", "date", "industry"]].copy()
    known["date"] = pd.to_datetime(known["date"]).astype("datetime64[ns]")
    fresh = snapshot.copy()
    fresh["date"] = pd.to_datetime(fresh["date"]).astype("datetime64[ns]")
    before = pd.merge_asof(
        fresh.sort_values("date"), known.sort_values("date").rename(columns={"industry": "previous"}),
        on="date", by="symbol", direction="backward",
    )
    changed = before[before["previous"].isna() | before["previous"].ne(before["industry"])]
    return changed.drop(columns=["previous"]).reset_index(drop=True)


def industry_on(days: pd.DataFrame, changes: pd.DataFrame, level: str = "industry") -> pd.Series:
    """Each (symbol, date) row's industry as known that day; aligned with ``days``.

    Before a stock's first recorded classification its first one is used: a company's industry is
    known when it lists, the vendor's quarterly snapshots simply pick it up a little later.
    Stocks never classified stay missing. ``level`` is ``industry`` (division) or ``sector``.
    """

    if level not in {"industry", "sector"}:
        raise ValueError("行业层级只能是 industry 或 sector")
    result = pd.Series(pd.NA, index=days.index, dtype="object")
    if days.empty or changes.empty or level not in changes.columns:
        return result
    known = changes.dropna(subset=[level])[["symbol", "date", level]].copy()
    known["date"] = pd.to_datetime(known["date"]).astype("datetime64[ns]")
    known = known.sort_values(["date", "symbol"])
    asked = pd.DataFrame({"symbol": days["symbol"].to_numpy(), "date": pd.to_datetime(days["date"]).astype("datetime64[ns]").to_numpy(),
                          "_row": range(len(days))}).sort_values("date")
    matched = pd.merge_asof(asked, known, on="date", by="symbol", direction="backward")
    first = known.drop_duplicates("symbol", keep="first").set_index("symbol")[level]
    matched[level] = matched[level].where(matched[level].notna(), matched["symbol"].map(first))
    result.iloc[matched["_row"].to_numpy()] = matched[level].to_numpy()
    return result
