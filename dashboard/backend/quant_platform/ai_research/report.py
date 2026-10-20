"""The structured part of a stock analysis, from local data only and without any model.

``stock_facts`` lists every number; this module turns the same day's data into a report a reader
can follow:

- a one-sentence summary per section, written from fixed templates (it describes, never advises);
- a checklist of things worth a look, each with the rule that was checked;
- the last eight quarterly reports side by side, with how each ratio moved;
- the closest peers in the industry by size, next to the industry median;
- where the stock ranks on the built-in factors, against the market and its industry;
- the data for three charts: a year of prices with moving averages and dated events, the
  valuation history, and the quarterly trend.

Everything stays point in time: prices up to the day, reports published by the day, the industry
and index lists in force on the day.
"""

from __future__ import annotations

import logging
import math
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

import pandas as pd

from quant_platform.data.extras import extra_columns
from quant_platform.data.index_constituents import INDEX_UNIVERSES, stored_lists
from quant_platform.data.industry import EXPOSURES_TABLE

logger = logging.getLogger(__name__)

REPORT_VERSION = 1
QUARTERS = 8
PEER_ROWS = 6
MIN_PEERS = 5
MIN_MARKET = 30
CHART_DAYS = 250
TOP_SHARE, BOTTOM_SHARE = 0.8, 0.2
LOW_AMOUNT = 5e7                  # 近 20 日平均成交额低于 5000 万元：大额买卖可能影响价格
DEBT_ABOVE_PEERS = 0.20           # 资产负债率比同行中位数高 20 个百分点
PROFIT_DROP = -0.30
DEEP_DRAWDOWN = -0.40
RECENT_DAYS = 20
QUARTER_NAMES = {3: "一季报", 6: "半年报", 9: "三季报", 12: "年报"}


def _finite(x: Any) -> bool:
    try:
        return x is not None and not pd.isna(x) and math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _num(x: Any, digits: int = 4) -> float | None:
    return round(float(x), digits) if _finite(x) else None


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _signed(x: float) -> str:
    return f"{x * 100:+.1f}%"


def _share(values: pd.Series, symbol: str, minimum: int) -> tuple[float, int] | None:
    """Share of the other stocks with a lower value (ties count half), and how many were compared."""

    values = values.dropna()
    values = values[values.map(_finite)]
    if symbol not in values.index or len(values) < minimum:
        return None
    own = values[symbol]
    below = int((values < own).sum())
    equal = int((values == own).sum()) - 1
    return (below + equal / 2) / (len(values) - 1), len(values)


def clean(value: Any) -> Any:
    """JSON-safe copy: NaN and infinities become None, numpy numbers and booleans plain Python ones."""

    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(item) for item in value]
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def period_name(stat: pd.Timestamp) -> str:
    return f"{stat.year}{QUARTER_NAMES.get(stat.month, stat.strftime('%m-%d'))}"


# --------------------------------------------------------------------------- #
# 财务趋势
# --------------------------------------------------------------------------- #

def published_reports(reports: pd.DataFrame, trade_ts: pd.Timestamp) -> pd.DataFrame:
    """Reports published by the day, one per period (the newest publication), oldest first."""

    frame = reports.dropna(subset=["pub_date"]).copy()
    if frame.empty:
        return frame
    frame["pub_date"] = pd.to_datetime(frame["pub_date"])
    frame["stat_date"] = pd.to_datetime(frame["stat_date"])
    keys = ["symbol", "stat_date"] if "symbol" in frame.columns else ["stat_date"]
    frame = frame[frame["pub_date"] <= trade_ts].sort_values([*keys, "pub_date"])
    return frame.drop_duplicates(keys, keep="last").sort_values([*keys])


def _trend(values: list[float | None]) -> str:
    """How the last four values moved: 连续上升 / 连续下降 / 基本持平 / 有升有降 / 数据不足."""

    recent = [v for v in values[-4:] if v is not None]
    if len(recent) < 3:
        return "数据不足"
    steps = [b - a for a, b in zip(recent, recent[1:])]
    if all(abs(step) < 1e-9 for step in steps):
        return "基本持平"
    if all(step > 0 for step in steps):
        return "连续上升"
    if all(step < 0 for step in steps):
        return "连续下降"
    return "有升有降"


def financial_trend(reports: pd.DataFrame, trade_ts: pd.Timestamp) -> dict[str, Any] | None:
    frame = published_reports(reports, trade_ts)
    if frame.empty:
        return None
    revenue = dict(zip(frame["stat_date"], frame.get("revenue", pd.Series(dtype=float))))
    rows = []
    for _, report in frame.tail(QUARTERS).iterrows():
        stat = report["stat_date"]
        before = revenue.get(stat - pd.DateOffset(years=1))
        own = report.get("revenue")
        revenue_yoy = float(own) / float(before) - 1 if _finite(own) and _finite(before) and float(before) > 0 else None
        growth = next((report.get(key) for key in ("yoy_parent_net_profit", "yoy_net_profit") if _finite(report.get(key))), None)
        leverage = report.get("asset_to_equity")
        debt = 1 - 1 / float(leverage) if _finite(leverage) and float(leverage) > 0 else None
        rows.append({
            "period": period_name(stat), "stat_date": stat.date().isoformat(), "pub_date": report["pub_date"].date().isoformat(),
            "revenue_yoy": _num(revenue_yoy), "profit_yoy": _num(growth), "gross_margin": _num(report.get("gross_margin")),
            "net_margin": _num(report.get("net_margin")), "roe": _num(report.get("roe_avg")), "debt_ratio": _num(debt),
        })
    # 净资产收益率是年初至报告期累计的，不同季度之间不能直接比，所以不算它的走向。
    trends = {key: _trend([row[key] for row in rows]) for key in ("revenue_yoy", "profit_yoy", "gross_margin", "net_margin", "debt_ratio")}
    return {"rows": rows, "trends": trends}


# --------------------------------------------------------------------------- #
# 同行对比
# --------------------------------------------------------------------------- #

def _report_on(frame: pd.DataFrame, trade_ts: pd.Timestamp) -> pd.DataFrame:
    """The newest report in force on the day for each symbol (published by then, at most a year old)."""

    published = published_reports(frame, trade_ts) if not frame.empty else frame
    if published.empty:
        return published
    published = published[(trade_ts - published["pub_date"]).dt.days <= 370]
    return published.sort_values(["symbol", "stat_date"]).drop_duplicates("symbol", keep="last").set_index("symbol")


def peer_table(repository: Any, symbol: str, peers: list[str], today: pd.DataFrame, prices: pd.DataFrame,
               trade_ts: pd.Timestamp, names: dict[str, str], industry: str) -> dict[str, Any] | None:
    if len(peers) < MIN_PEERS:
        return None
    members = sorted(set(peers) | {symbol})
    close = today.set_index("symbol")["raw_close"].reindex(members)
    indicators = repository.get_daily_indicators(members, trade_ts.date(), trade_ts.date(), columns=["pe_ttm", "pb_mrq"])
    indicators = indicators.set_index("symbol") if not indicators.empty else pd.DataFrame(index=pd.Index([], name="symbol"))
    reports = _report_on(repository.get_fundamentals(members), trade_ts)
    ret_60 = (prices.iloc[-1] / prices.iloc[-61] - 1) if len(prices) > 60 else pd.Series(dtype=float)

    def value(frame: pd.DataFrame, row: str, column: str) -> Any:
        return frame.at[row, column] if row in frame.index and column in frame.columns else None

    table = []
    for member in members:
        shares = value(reports, member, "total_shares")
        cap = float(close.get(member)) * float(shares) if _finite(close.get(member)) and _finite(shares) else None
        leverage = value(reports, member, "asset_to_equity")
        growth = next((value(reports, member, key) for key in ("yoy_parent_net_profit", "yoy_net_profit")
                       if _finite(value(reports, member, key))), None)
        pe = value(indicators, member, "pe_ttm")
        table.append({
            "symbol": member, "name": names.get(member, member), "self": member == symbol,
            "market_cap": _num(cap, 0), "pe": _num(pe, 2) if _finite(pe) and float(pe) > 0 else None,
            "pb": _num(value(indicators, member, "pb_mrq"), 2), "roe": _num(value(reports, member, "roe_avg")),
            "profit_yoy": _num(growth),
            "debt_ratio": _num(1 - 1 / float(leverage)) if _finite(leverage) and float(leverage) > 0 else None,
            "ret_60d": _num(ret_60.get(member)),
        })
    frame = pd.DataFrame(table).set_index("symbol")
    metrics = ["market_cap", "pe", "pb", "roe", "profit_yoy", "debt_ratio", "ret_60d"]
    median = {key: _num(frame[key].dropna().median()) if frame[key].notna().any() else None for key in metrics}
    ranks = {}
    for key in metrics:
        found = _share(frame[key], symbol, MIN_PEERS)
        if found is not None:
            ranks[key] = round(found[0], 4)
    # 挑市值最接近的几家；没有市值时按近 60 日涨跌最接近的挑。
    own_cap = frame.at[symbol, "market_cap"]
    others = frame.drop(index=symbol)
    if _finite(own_cap) and others["market_cap"].notna().any():
        distance = (others["market_cap"].map(lambda c: abs(math.log(c) - math.log(own_cap)) if _finite(c) and c > 0 else math.inf))
    else:
        distance = (others["ret_60d"] - frame.at[symbol, "ret_60d"]).abs().fillna(math.inf)
    chosen = list(distance.sort_values().index[:PEER_ROWS])
    rows = [dict(frame.loc[symbol].to_dict(), symbol=symbol)]
    rows += [dict(frame.loc[peer].to_dict(), symbol=peer) for peer in chosen]
    rows.sort(key=lambda row: -(row["market_cap"] or 0))
    return {"industry": industry, "count": len(members), "rows": rows, "median": median, "ranks": ranks}


# --------------------------------------------------------------------------- #
# 因子画像
# --------------------------------------------------------------------------- #

FACTOR_DAYS = 60
FACTOR_CACHE_SIZE = 8
_FACTOR_CACHE: OrderedDict[tuple, pd.DataFrame] = OrderedDict()
_FACTOR_LOCK = threading.Lock()
_PENDING: set[tuple] = set()
# 测试里设为 False：现算，不开后台线程。
COMPUTE_IN_BACKGROUND = True
# 算好的全市场因子值存在这里（应用启动时用 ``configure`` 设置），重启后不用重算。
_STORE: Path | None = None


def configure(directory: Path | str | None) -> None:
    global _STORE
    _STORE = Path(directory) if directory else None


def _data_stamp(root: Path) -> str:
    """Changes whenever a local data file is written: the newest file time and the file count."""

    files = list(Path(root).rglob("*.parquet"))
    return f"{len(files)}:{max((f.stat().st_mtime_ns for f in files), default=0)}"


def _key(repository: Any, trade_ts: pd.Timestamp) -> tuple:
    root = getattr(repository, "root", None)
    return (str(root or id(repository)), pd.Timestamp(trade_ts).normalize(), _data_stamp(root) if root else "")


def _stored_path(key: tuple) -> Path | None:
    if _STORE is None or not key[2]:      # 没有数据目录（例如测试用的假仓库）时不存文件
        return None
    return _STORE / f"{key[1].date().isoformat()}_{key[2].replace(':', '-')}.parquet"


def compute_cross_section(repository: Any, trade_ts: pd.Timestamp) -> pd.DataFrame:
    """Every built-in factor's value for every stock on the day: ``symbol`` x factor name.

    Built-in factors need at most 21 trading days of history, so only the last ``FACTOR_DAYS``
    trading days are read. Factors whose data (valuation, reports) is missing are left out."""

    from quant_platform.factors.builtins import builtin_factors

    factors = builtin_factors()
    trade_ts = pd.Timestamp(trade_ts).normalize()
    window = repository.get_daily_bars(start_date=(trade_ts - pd.Timedelta(days=FACTOR_DAYS * 2 + 30)).date(), end_date=trade_ts.date())
    days = sorted(pd.to_datetime(window["trade_date"]).unique())[-max(FACTOR_DAYS, max(f.min_history for f in factors) * 2):]
    window = window[pd.to_datetime(window["trade_date"]) >= days[0]]
    extras = extra_columns(field for factor in factors for field in factor.required_fields)
    enriched = None
    if extras:
        try:
            enriched = repository.get_daily_bars(start_date=pd.Timestamp(days[0]).date(), end_date=trade_ts.date(), extras=extras)
        except Exception as exc:  # noqa: BLE001 - 估值、财务或行业数据缺失时只算行情类因子
            logger.info("factor profile without extra data: %s", exc)
    columns = {}
    for factor in factors:
        wanted = extra_columns(factor.required_fields)
        bars = enriched if wanted else window
        if bars is None or not set(factor.required_fields) <= set(bars.columns) or not all(bars[c].notna().any() for c in wanted):
            continue
        try:
            values = factor.compute(bars)
        except Exception as exc:  # noqa: BLE001 - 一个因子算不出来不影响其他因子
            logger.info("factor %s failed: %s", factor.name, exc)
            continue
        values = values[pd.to_datetime(values["date"]).dt.normalize() == trade_ts]
        columns[factor.name] = values.set_index("symbol")["value"]
    table = pd.DataFrame(columns)
    table.index.name = "symbol"
    return table


def _remember(key: tuple, table: pd.DataFrame) -> None:
    with _FACTOR_LOCK:
        _FACTOR_CACHE[key] = table
        _FACTOR_CACHE.move_to_end(key)
        while len(_FACTOR_CACHE) > FACTOR_CACHE_SIZE:
            _FACTOR_CACHE.popitem(last=False)


def known_cross_section(repository: Any, trade_ts: pd.Timestamp, *, exact: bool = True) -> pd.DataFrame | None:
    """The day's factor values if already computed (in memory or on disk); never computes.

    ``exact=False`` also accepts values computed for the same day on slightly older data (for
    example before a later report download): while a data job keeps rewriting files, a profile
    can still be shown instead of waiting forever."""

    key = _key(repository, trade_ts)
    with _FACTOR_LOCK:
        if key in _FACTOR_CACHE:
            _FACTOR_CACHE.move_to_end(key)
            return _FACTOR_CACHE[key]
        if not exact:
            same_day = [k for k in _FACTOR_CACHE if k[:2] == key[:2]]
            if same_day:
                return _FACTOR_CACHE[same_day[-1]]
    path = _stored_path(key)
    if path is not None and not path.exists() and not exact:
        older = sorted(path.parent.glob(f"{key[1].date().isoformat()}_*.parquet"), key=lambda f: f.stat().st_mtime)
        path = older[-1] if older else None
    if path is not None and path.exists():
        try:
            table = pd.read_parquet(path)
        except Exception:  # noqa: BLE001 - 文件坏了就重算
            return None
        if path == _stored_path(key):
            _remember(key, table)
        return table
    return None


def ensure_cross_section(repository: Any, trade_ts: pd.Timestamp, *, background: bool = True, exact: bool = False) -> pd.DataFrame | None:
    """The day's factor values; computes them when missing, in a background thread by default
    (then returns None, and a later call finds them). Only one computation per day runs at a time."""

    table = known_cross_section(repository, trade_ts, exact=exact)
    if table is not None:
        return table
    key = _key(repository, trade_ts)

    def work() -> pd.DataFrame | None:
        try:
            result = compute_cross_section(repository, key[1])
            path = _stored_path(key)
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix(".tmp")
                result.to_parquet(temporary)
                temporary.replace(path)
                for old in sorted(path.parent.glob("*.parquet"))[:-30]:   # 只留最近 30 份
                    old.unlink(missing_ok=True)
            _remember(key, result)
            return result
        except Exception:  # noqa: BLE001 - 后台计算失败只记日志
            logger.exception("factor cross-section failed for %s", key[1].date())
            return None
        finally:
            with _FACTOR_LOCK:
                _PENDING.discard(key)

    with _FACTOR_LOCK:
        if key in _PENDING:
            return None
        _PENDING.add(key)
    if not background or not COMPUTE_IN_BACKGROUND:
        return work()
    threading.Thread(target=work, name="factor-profile", daemon=True).start()
    return None


def factor_profile_from(table: pd.DataFrame, symbol: str, peers: list[str]) -> dict[str, Any] | None:
    from quant_platform.factors.builtins import builtin_factors

    if symbol not in table.index:
        return None
    missing = [factor.display_name for factor in builtin_factors() if factor.name not in table.columns]
    peers_in = [p for p in peers if p in table.index]
    items = []
    for factor in builtin_factors():
        if factor.name not in table.columns or not _finite(table.at[symbol, factor.name]):
            continue
        market = _share(table[factor.name], symbol, MIN_MARKET)
        industry = _share(table[factor.name].reindex(peers_in), symbol, MIN_PEERS) if len(peers_in) >= MIN_PEERS else None
        items.append({
            "name": factor.name, "display_name": factor.display_name, "category": factor.category, "direction": factor.direction,
            "value": _num(table.at[symbol, factor.name], 6),
            "market_share": round(market[0], 4) if market else None, "market_count": market[1] if market else 0,
            "industry_share": round(industry[0], 4) if industry else None,
        })
    return {"items": items, "missing": missing} if items else None


def factor_profile(repository: Any, symbol: str, peers: list[str], trade_ts: pd.Timestamp, complete: bool) -> dict[str, Any] | None:
    """The factor profile, or ``{"pending": True, ...}`` while the day's values are computed in the background."""

    if not complete:
        return {"unavailable": "这一天平台只有一部分股票的行情，无法和全市场比较因子。"}
    try:
        table = ensure_cross_section(repository, trade_ts)
    except Exception as exc:  # noqa: BLE001 - 因子画像失败不影响其余部分
        logger.warning("factor profile failed for %s: %s", symbol, exc)
        return None
    if table is None:
        return {"pending": True, "trade_date": trade_ts.date().isoformat(), "peers": sorted(set(peers))}
    return factor_profile_from(table, symbol, peers)


def fill_pending_factors(repository: Any, report: dict[str, Any], symbol: str) -> bool:
    """When a saved report's factor profile was still being computed, fill it in if it is ready now.

    Returns True when the report changed (the caller saves it)."""

    pending = (report or {}).get("factors") or {}
    if not pending.get("pending"):
        return False
    table = ensure_cross_section(repository, pd.Timestamp(pending["trade_date"]))
    if table is None:
        return False
    report["factors"] = clean(factor_profile_from(table, symbol, list(pending.get("peers") or [])))
    summaries_list = [item for item in report.get("summaries", []) if item.get("key") != "factors"]
    extra = factor_summary(report["factors"])
    if extra:
        at = next((i for i, item in enumerate(summaries_list) if item.get("key") == "events"), len(summaries_list))
        summaries_list.insert(at, extra)
    report["summaries"] = summaries_list
    return True


# --------------------------------------------------------------------------- #
# 图表
# --------------------------------------------------------------------------- #

def price_chart(series: pd.Series) -> list[list[Any]]:
    series = series.dropna()
    ma20, ma60 = series.rolling(20).mean(), series.rolling(60).mean()
    tail = series.index[-CHART_DAYS:]
    return [[pd.Timestamp(day).date().isoformat(), _num(series[day], 3), _num(ma20[day], 3), _num(ma60[day], 3)] for day in tail]


def events(repository: Any, symbol: str, own: pd.DataFrame, reports: pd.DataFrame, start: pd.Timestamp,
           trade_ts: pd.Timestamp) -> list[dict[str, str]]:
    """Dated events in the chart window: dividends and splits, report publications, index changes,
    industry changes and ST changes."""

    found: list[dict[str, str]] = []

    def add(day: Any, kind: str, text: str) -> None:
        found.append({"date": pd.Timestamp(day).date().isoformat(), "kind": kind, "text": text})

    actions = repository.read_table("corporate_actions")
    if not actions.empty:
        rows = actions[actions["symbol"] == symbol].copy()
        rows["ex_date"] = pd.to_datetime(rows["ex_date"])
        for _, row in rows[(rows["ex_date"] >= start) & (rows["ex_date"] <= trade_ts)].iterrows():
            parts = []
            if _finite(row.get("cash_per_share")) and float(row["cash_per_share"]) > 0:
                parts.append(f"每 10 股派 {float(row['cash_per_share']) * 10:.2f} 元")
            if _finite(row.get("share_multiplier")) and float(row["share_multiplier"]) > 1:
                parts.append(f"每 10 股送转 {(float(row['share_multiplier']) - 1) * 10:.1f} 股")
            add(row["ex_date"], "action", "除权除息：" + ("，".join(parts) or "有记录"))
    for _, report in published_reports(reports, trade_ts).iterrows():
        if report["pub_date"] >= start:
            add(report["pub_date"], "report", f"发布{period_name(report['stat_date'])}")
    constituents = repository.read_table("index_constituents")
    for index_symbol, (label, _) in INDEX_UNIVERSES.items():
        lists = sorted((day, members) for day, members in stored_lists(constituents, index_symbol).items() if day <= trade_ts.date())
        for (_, before), (day, after) in zip(lists, lists[1:]):
            if pd.Timestamp(day) < start:
                continue
            if symbol in after and symbol not in before:
                add(day, "index", f"调入{label}")
            elif symbol in before and symbol not in after:
                add(day, "index", f"调出{label}")
    exposures = repository.read_table(EXPOSURES_TABLE)
    if not exposures.empty:
        rows = exposures[exposures["symbol"] == symbol].copy()
        rows["date"] = pd.to_datetime(rows["date"])
        rows = rows.sort_values("date")
        changed = rows[rows["industry"] != rows["industry"].shift()]
        for _, row in changed.iloc[1:].iterrows():
            if start <= row["date"] <= trade_ts:
                add(row["date"], "industry", f"行业改为{row['industry']}")
    if "is_st" in own.columns:
        status = own[["trade_date", "is_st"]].dropna()
        flips = status[status["is_st"].astype(bool) != status["is_st"].astype(bool).shift()]
        for _, row in flips.iloc[1:].iterrows():
            if row["trade_date"] >= start:
                add(row["trade_date"], "st", "被实施 ST" if bool(row["is_st"]) else "撤销 ST")
    return sorted(found, key=lambda item: item["date"])


def valuation_chart(repository: Any, symbol: str, trade_ts: pd.Timestamp, years: int = 3) -> dict[str, Any] | None:
    start = (trade_ts - pd.DateOffset(years=years)).date()
    history = repository.get_daily_indicators([symbol], start, trade_ts.date(), columns=["pe_ttm", "pb_mrq"])
    if history.empty:
        return None
    history = history.sort_values("trade_date")
    result: dict[str, Any] = {"points": [], "bands": {}, "start": pd.Timestamp(history["trade_date"].iloc[0]).date().isoformat()}
    sampled = history.iloc[::5]
    if not sampled.empty and sampled.index[-1] != history.index[-1]:
        sampled = pd.concat([sampled, history.iloc[[-1]]])
    for _, row in sampled.iterrows():
        pe, pb = row.get("pe_ttm"), row.get("pb_mrq")
        result["points"].append([pd.Timestamp(row["trade_date"]).date().isoformat(),
                                 _num(pe, 2) if _finite(pe) and float(pe) > 0 else None, _num(pb, 3) if _finite(pb) and float(pb) > 0 else None])
    for key in ("pe_ttm", "pb_mrq"):
        values = history[key].dropna()
        values = values[values > 0]
        if len(values) >= 120:
            current = history[key].iloc[-1]
            result["bands"][key] = {
                "p20": _num(values.quantile(0.2), 3), "p50": _num(values.quantile(0.5), 3), "p80": _num(values.quantile(0.8), 3),
                "current": _num(current, 3) if _finite(current) and float(current) > 0 else None,
                "share": round(float((values < current).mean()), 4) if _finite(current) and float(current) > 0 else None,
            }
    return result if result["points"] else None


# --------------------------------------------------------------------------- #
# 需要留意的清单
# --------------------------------------------------------------------------- #

def checks(facts: dict[str, Any], own: pd.DataFrame, missing_groups: set[str], peers: dict[str, Any] | None,
           trend: dict[str, Any] | None) -> list[dict[str, str]]:
    """Each rule: warn (需要留意) / ok (没有发现) / unknown (数据不足)."""

    def value(key: str) -> float | None:
        fact = facts.get(key)
        return fact.value if fact is not None else None

    items: list[dict[str, str]] = []

    def add(key: str, label: str, rule: str, state: str, text: str) -> None:
        items.append({"key": key, "label": label, "rule": rule, "state": state, "text": text})

    st = value("is_st")
    add("st", "风险警示（ST）", "当天是否被实施 ST 或 *ST", "unknown" if st is None else ("warn" if st else "ok"),
        "是 ST 股，有退市风险警示" if st else ("不是 ST 股" if st is not None else "没有这项数据"))
    years = value("list_date")
    add("new_listing", "上市时间", "上市是否满一年", "unknown" if years is None else ("warn" if years < 1 else "ok"),
        "上市不满一年，历史数据较短" if years is not None and years < 1 else (f"上市 {years:.0f} 年" if years is not None else "没有上市日期"))
    recent = own.tail(RECENT_DAYS)
    suspended = int(recent["is_suspended"].eq(True).sum()) if "is_suspended" in recent else 0
    add("suspended", "停牌", f"近 {RECENT_DAYS} 个交易日停牌是否达到 3 天", "warn" if suspended >= 3 else "ok",
        f"近 {RECENT_DAYS} 个交易日停牌 {suspended} 天")
    if {"raw_close", "down_limit"} <= set(recent.columns):
        closes = recent.dropna(subset=["raw_close", "down_limit"])
        limit_down = int((closes["raw_close"] <= closes["down_limit"] + 0.005).sum())
        add("limit_down", "跌停", f"近 {RECENT_DAYS} 个交易日跌停是否达到 2 次", "warn" if limit_down >= 2 else "ok",
            f"近 {RECENT_DAYS} 个交易日收盘跌停 {limit_down} 次")
    amount = value("amount_20d")
    add("liquidity", "成交额", "近 20 日平均成交额是否低于 5000 万元",
        "unknown" if amount is None else ("warn" if amount < LOW_AMOUNT else "ok"),
        "没有成交额数据" if amount is None else (f"近 20 日平均 {amount / 1e8:.2f} 亿元" + ("，成交较少，大额买卖可能影响价格" if amount < LOW_AMOUNT else "")))
    pe = value("pe_ttm")
    if "估值" in missing_groups or pe is None:
        add("loss", "盈利", "最近四个季度合计是否亏损（市盈率为负）", "unknown", "没有估值数据")
    else:
        add("loss", "盈利", "最近四个季度合计是否亏损（市盈率为负）", "warn" if pe <= 0 else "ok",
            "最近四个季度合计亏损" if pe <= 0 else "最近四个季度合计盈利")
    if "财务" in missing_groups:
        add("report", "财报", "当天是否有一年内公布的财报", "unknown", "平台还没有这只股票当时已公告的财报")
    else:
        growth = value("profit_growth")
        add("profit_drop", "利润变化", "最新财报的净利润同比是否下降超过 30%",
            "unknown" if growth is None else ("warn" if growth < PROFIT_DROP else "ok"),
            "没有利润增长数据" if growth is None else f"净利润同比 {_signed(growth)}")
        debt, median = value("debt_ratio"), (peers or {}).get("median", {}).get("debt_ratio")
        if debt is not None and median is not None:
            high = debt - median > DEBT_ABOVE_PEERS
            add("debt", "负债", "资产负债率是否比同行业中位数高 20 个百分点以上", "warn" if high else "ok",
                f"资产负债率 {_pct(debt)}，同行业中位数 {_pct(median)}")
        else:
            add("debt", "负债", "资产负债率是否比同行业中位数高 20 个百分点以上", "unknown", "没有同行可以比较")
    drawdown = value("from_high_250d")
    add("drawdown", "距一年高点", "是否比近一年最高价低 40% 以上",
        "unknown" if drawdown is None else ("warn" if drawdown < DEEP_DRAWDOWN else "ok"),
        "历史不到半年，无法判断" if drawdown is None else f"距近一年最高价 {_signed(drawdown)}")
    if trend and trend["trends"].get("profit_yoy") == "连续下降":
        add("profit_trend", "利润增长走向", "最近四份财报的净利润同比是否一直在下降", "warn", "最近四份财报的净利润同比一直在下降")
    return items


# --------------------------------------------------------------------------- #
# 每一节的一句话小结（固定句式，只描述，不给方向）
# --------------------------------------------------------------------------- #

def factor_summary(factors: dict[str, Any] | None) -> dict[str, str] | None:
    """因子画像的一句话：哪些因子的数值处在全市场前 20% 和后 20%。"""

    if not factors or not factors.get("items"):
        return None
    ranked = [item for item in factors["items"] if item["market_share"] is not None]
    if not ranked:
        return None
    high = [item["display_name"] for item in ranked if item["market_share"] >= TOP_SHARE]
    low = [item["display_name"] for item in ranked if item["market_share"] <= BOTTOM_SHARE]
    parts = [f"在 {len(ranked)} 个内置因子中"]
    if high:
        parts.append(f"数值处在全市场前 20% 的有{'、'.join(high)}")
    if low:
        parts.append(f"处在后 20% 的有{'、'.join(low)}")
    if not high and not low:
        parts.append("没有处在全市场前 20% 或后 20% 的")
    return {"key": "factors", "title": "因子画像", "text": "，".join(parts) + "。"}


def summaries(facts: dict[str, Any], trend: dict[str, Any] | None, peers: dict[str, Any] | None,
              factors: dict[str, Any] | None) -> list[dict[str, str]]:
    def v(key: str) -> float | None:
        fact = facts.get(key)
        return fact.value if fact is not None else None

    def t(key: str) -> str | None:
        fact = facts.get(key)
        return fact.text if fact is not None else None

    out: list[dict[str, str]] = []

    def add(key: str, title: str, parts: list[str | None]) -> None:
        text = "，".join(part for part in parts if part)
        if text:
            out.append({"key": key, "title": title, "text": text + "。"})

    basic = [t("industry") and f"属于{t('industry')}", t("indexes") and (t("indexes") if t("indexes").startswith("不在") else f"是{t('indexes')}成分股"),
             t("list_date") and f"{t('list_date').split('（')[-1].rstrip('）')}", "是 ST 股" if v("is_st") else None]
    add("basic", "基本信息", basic)
    price = []
    if v("ret_60d") is not None:
        price.append(f"近 60 个交易日{'上涨' if v('ret_60d') >= 0 else '下跌'} {abs(v('ret_60d')) * 100:.1f}%")
    if t("ma60_gap"):
        price.append(f"收盘价{t('ma60_gap').replace('在均线', '在 60 日均线')}")
    if v("from_high_250d") is not None:
        price.append(f"距近一年最高价 {_signed(v('from_high_250d'))}")
    if v("volatility_60d") is not None:
        rank = v("rank_volatility_60d")
        price.append(f"近 60 日年化波动率 {_pct(v('volatility_60d'))}" + (f"，高于全市场 {rank * 100:.0f}% 的股票" if rank is not None else ""))
    add("price", "价格走势", price)
    trade = []
    if v("amount_20d") is not None:
        trade.append(f"近 20 日平均成交额 {v('amount_20d') / 1e8:.2f} 亿元")
    if v("amount_ratio") is not None:
        trade.append(f"当日为平均的 {v('amount_ratio'):.1f} 倍")
    if v("turnover_rate") is not None:
        trade.append(f"换手率 {v('turnover_rate'):.2f}%")
    add("trading", "成交", trade)
    market = []
    if v("rank_ret_20d") is not None:
        market.append(f"近 20 个交易日涨幅高于全市场 {v('rank_ret_20d') * 100:.0f}% 的股票")
    if v("rank_ret_250d") is not None:
        market.append(f"近一年涨幅高于 {v('rank_ret_250d') * 100:.0f}%")
    if v("industry_rank_ret_20d") is not None:
        market.append(f"近 20 日涨幅高于同行业 {v('industry_rank_ret_20d') * 100:.0f}% 的股票")
    add("market", "全市场比较", market)
    valuation = []
    if v("pe_ttm") is not None:
        valuation.append(f"市盈率（TTM）{t('pe_ttm')}" if v("pe_ttm") > 0 else "最近四个季度合计亏损，市盈率为负")
    if v("pe_position") is not None:
        valuation.append(f"高于自身近几年 {v('pe_position') * 100:.0f}% 的交易日")
    if v("industry_pe_median") is not None:
        valuation.append(f"同行业中位数 {v('industry_pe_median'):.1f}")
    if v("pb_mrq") is not None:
        valuation.append(f"市净率 {v('pb_mrq'):.2f}")
    add("valuation", "估值", valuation)
    finance = []
    if t("report"):
        finance.append(f"最新财报为{t('report').split('（')[0]}")
    if v("profit_growth") is not None:
        finance.append(f"净利润同比 {_signed(v('profit_growth'))}")
    if v("gross_margin") is not None:
        finance.append(f"毛利率 {_pct(v('gross_margin'))}")
    if v("debt_ratio") is not None:
        finance.append(f"资产负债率 {_pct(v('debt_ratio'))}")
    if trend:
        moves = trend["trends"]
        named = {"revenue_yoy": "营收增长", "profit_yoy": "利润增长", "gross_margin": "毛利率"}
        moved = [f"{label}{moves[key]}" for key, label in named.items() if moves.get(key) in ("连续上升", "连续下降")]
        if moved:
            finance.append("最近四份财报" + "、".join(moved))
    add("finance", "财务", finance)
    if peers and peers.get("ranks"):
        ranks = peers["ranks"]
        names = {"market_cap": "市值", "pe": "市盈率", "roe": "净资产收益率", "profit_yoy": "利润增长"}
        parts = [f"{label}高于 {ranks[key] * 100:.0f}% 的同行" for key, label in names.items() if key in ranks]
        add("peers", "同行对比", [f"同行业 {peers['count']} 只股票中，" + "，".join(parts)] if parts else [])
    factor_line = factor_summary(factors)
    if factor_line:
        out.append(factor_line)
    events_text = t("last_action")
    if events_text:
        add("events", "事件", [f"最近一年的分红送转：{events_text}" if v("last_action") == 0 else f"最近一次除权除息 {events_text}"])
    return out


def build_report(repository: Any, *, symbol: str, trade_ts: pd.Timestamp, window: pd.DataFrame, prices: pd.DataFrame,
                 peers: list[str], facts: dict[str, Any], missing: list[dict[str, str]], complete: bool = True) -> dict[str, Any]:
    """Everything above for one stock on one day. A part that fails or lacks data is left out."""

    own = window[window["symbol"] == symbol].sort_values("trade_date")
    master = repository.read_table("security_master")
    names = dict(zip(master["symbol"], master["name"])) if {"symbol", "name"} <= set(master.columns) else {}
    reports = repository.get_fundamentals([symbol])
    trend = financial_trend(reports, trade_ts) if not reports.empty else None
    today = window[window["trade_date"] == trade_ts]
    industry_fact = facts.get("industry")
    industry = industry_fact.text.split("（")[0] if industry_fact is not None else ""
    try:
        peer = peer_table(repository, symbol, peers, today, prices, trade_ts, names, industry)
    except Exception as exc:  # noqa: BLE001 - 同行对比失败不影响其余部分
        logger.warning("peer table failed for %s: %s", symbol, exc)
        peer = None
    factors = factor_profile(repository, symbol, peers, trade_ts, complete)
    series = prices[symbol].dropna() if symbol in prices.columns else pd.Series(dtype=float)
    chart_start = pd.Timestamp(series.index[-CHART_DAYS:][0]) if len(series) else trade_ts
    return clean({
        "version": REPORT_VERSION,
        "summaries": summaries(facts, trend, peer, factors),
        "checks": checks(facts, own, {item["group"] for item in missing}, peer, trend),
        "financial_trend": trend,
        "peers": peer,
        "factors": factors,
        "charts": {
            "prices": price_chart(series),
            "events": events(repository, symbol, own, reports, chart_start, trade_ts),
            "valuation": valuation_chart(repository, symbol, trade_ts),
        },
    })


# --------------------------------------------------------------------------- #
# 和上次分析对比
# --------------------------------------------------------------------------- #

COMPARED = ("close", "ret_20d", "ret_60d", "from_high_250d", "volatility_60d", "amount_20d", "turnover_rate", "pe_ttm",
            "pe_position", "pb_mrq", "roe_avg", "gross_margin", "profit_growth", "debt_ratio", "rank_ret_20d", "rank_volatility_60d")


def compare_facts(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    """Key numbers of two analyses of the same stock: what each was, what it is now."""

    old = {item["key"]: item for item in before.get("facts", [])}
    new = {item["key"]: item for item in after.get("facts", [])}
    changes = []
    for key in COMPARED:
        a, b = old.get(key), new.get(key)
        if not a or not b or a.get("value") is None or b.get("value") is None or a.get("text") == b.get("text"):
            continue
        changes.append({"key": key, "label": b["label"], "before": a["text"], "after": b["text"],
                        "delta": round(float(b["value"]) - float(a["value"]), 6)})
    return changes
