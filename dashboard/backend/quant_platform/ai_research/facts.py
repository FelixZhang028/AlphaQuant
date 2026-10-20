"""One stock's facts on one day, from local data only.

Every number the AI researcher may use is here, with the day it was known on. Nothing after the
day is read: prices up to the day, valuation on the day, the newest financial report already
published, the industry and the index lists in force. A part the local data does not have is
listed in ``missing`` with where to get it, instead of being guessed.

Price facts use adjusted closes, so an ex-dividend day is not a fall. Market comparisons are
among the stocks that traded that day.

``report`` holds the structured report built from the same data (``report.build_report``): section
summaries, a checklist, the quarterly trend, peers, the factor profile and chart data. The models
only ever read ``facts``.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

import pandas as pd

from quant_platform.data.index_constituents import INDEX_UNIVERSES, members_on, stored_lists
from quant_platform.data.industry import EXPOSURES_TABLE, industry_on

logger = logging.getLogger(__name__)

GROUPS = ("基本信息", "价格走势", "成交", "全市场比较", "估值", "财务", "事件")
# 一年约 250 个交易日；多读一些日历天，保证停牌过的股票也有一整年。
HISTORY_CALENDAR_DAYS = 400
VALUATION_YEARS = 3
MIN_PEERS = 5
MIN_MARKET = 30
# 当天有行情的股票少于近期常见数量的这个比例时，说明只更新了一部分股票，不做全市场比较。
COMPLETE_SHARE = 0.8
REPORT_MAX_AGE_DAYS = 370
REPORT_NAMES = {3: "一季报", 6: "半年报", 9: "三季报", 12: "年报"}


@dataclass(frozen=True)
class Fact:
    key: str
    group: str
    label: str
    text: str
    value: float | None = None
    as_of: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StockFacts:
    symbol: str
    name: str
    trade_date: date
    facts: list[Fact] = field(default_factory=list)
    missing: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)

    def by_key(self) -> dict[str, Fact]:
        return {fact.key: fact for fact in self.facts}

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "name": self.name, "trade_date": self.trade_date.isoformat(),
            "facts": [fact.to_dict() for fact in self.facts], "missing": list(self.missing), "notes": list(self.notes),
            "report": dict(self.report),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StockFacts:
        return cls(
            symbol=data["symbol"], name=data.get("name", ""), trade_date=date.fromisoformat(data["trade_date"]),
            facts=[Fact(**item) for item in data.get("facts", [])],
            missing=list(data.get("missing", [])), notes=list(data.get("notes", [])),
            report=dict(data.get("report") or {}),
        )


def _signed(x: float) -> str:
    return f"{x * 100:+.1f}%"


def _plain(x: float) -> str:
    return f"{x * 100:.1f}%"


def _yi(x: float) -> str:
    return f"{x / 1e8:.2f} 亿元"


def _finite(x: Any) -> bool:
    try:
        return x is not None and not pd.isna(x) and math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _position(values: pd.Series, symbol: str, minimum: int) -> tuple[float, int] | None:
    """Share of the other stocks whose value is below this one's (ties count half), and how many were compared."""

    values = values.dropna()
    if symbol not in values.index or len(values) < minimum:
        return None
    own = values[symbol]
    below = int((values < own).sum())
    equal = int((values == own).sum()) - 1
    return (below + equal / 2) / (len(values) - 1), len(values)


def industry_name(code: str) -> str:
    """'C27医药制造业' -> '医药制造业'."""

    return re.sub(r"^[A-Z]\d*", "", str(code)).strip() or str(code)


class _Builder:
    def __init__(self, symbol: str, name: str, trade_date: date) -> None:
        self.result = StockFacts(symbol=symbol, name=name, trade_date=trade_date)
        self.day = trade_date.isoformat()

    def add(self, key: str, group: str, label: str, text: str, value: float | None = None, as_of: str | None = None) -> None:
        number = float(value) if _finite(value) else None
        self.result.facts.append(Fact(key, group, label, text, number, as_of or self.day))

    def lack(self, group: str, reason: str) -> None:
        self.result.missing.append({"group": group, "reason": reason})


def stock_facts(repository: Any, symbol: str, day: date | None = None, *, name: str = "", with_report: bool = True) -> StockFacts:
    """The facts of ``symbol`` on its last trading day on or before ``day`` (default: the newest local day)."""

    bounds = repository.daily_bar_bounds()
    if bounds is None:
        raise ValueError("平台还没有行情数据，管理员更新后就能分析。")
    newest = bounds[1]
    asked = day or newest
    end = min(asked, newest)
    window = repository.get_daily_bars(start_date=end - timedelta(days=HISTORY_CALENDAR_DAYS), end_date=end)
    own = window[window["symbol"] == symbol].sort_values("trade_date")
    if own.empty:
        raise ValueError(f"本地没有 {symbol} 在 {end} 以前一年内的行情，平台更新这只股票的行情后就能分析。")
    last = own.iloc[-1]
    trade_ts = pd.Timestamp(last["trade_date"]).normalize()
    builder = _Builder(symbol, name or symbol, trade_ts.date())
    notes = builder.result.notes
    if asked > newest:
        notes.append(f"本地行情只到 {newest}，按 {trade_ts.date()} 的数据分析。")
    if trade_ts.date() < end:
        market_days = window.loc[window["trade_date"] <= pd.Timestamp(end), "trade_date"]
        if not market_days.empty and pd.Timestamp(market_days.max()) > trade_ts:
            notes.append(f"这只股票 {trade_ts.date()} 以后没有行情（停牌或退市），按 {trade_ts.date()} 的数据分析。")
        elif asked <= newest:
            notes.append(f"{asked} 不是交易日，按前一个交易日 {trade_ts.date()} 的数据分析。")

    window = window[window["trade_date"] <= trade_ts]
    today = window[window["trade_date"] == trade_ts]
    active = today.loc[~today["is_suspended"].eq(True), "symbol"] if "is_suspended" in today else today["symbol"]
    prices = window.pivot_table(index="trade_date", columns="symbol", values="adjusted_close", aggfunc="last").sort_index().ffill()
    amounts = window.pivot_table(index="trade_date", columns="symbol", values="amount", aggfunc="last").sort_index()
    counts = window.groupby("trade_date")["symbol"].nunique()
    usual = float(counts.iloc[-60:].median())
    complete = len(active) >= COMPLETE_SHARE * usual
    listed = sorted(set(window["symbol"]))
    prices = prices.reindex(columns=prices.columns.intersection(active).union([symbol]))

    _basic(builder, repository, last, trade_ts)
    _trend(builder, prices[symbol].dropna(), last)
    _trading(builder, amounts.get(symbol, pd.Series(dtype=float)), last)
    peers = _industry(builder, repository, symbol, listed, trade_ts)
    if complete:
        _compare(builder, prices, amounts.reindex(columns=prices.columns), symbol, peers)
    else:
        builder.lack("全市场比较", f"{trade_ts.date()} 本地只有 {len(active)} 只股票的行情（平时约 {usual:.0f} 只），"
                     "无法和全市场比较。可以选择更早的日期，或等平台更新完全市场的行情。")
    _valuation(builder, repository, symbol, trade_ts, peers)
    _financials(builder, repository, symbol, trade_ts)
    _events(builder, repository, symbol, trade_ts)
    builder.result.facts.sort(key=lambda fact: GROUPS.index(fact.group))
    if with_report:
        from quant_platform.ai_research.report import build_report

        try:
            builder.result.report = build_report(
                repository, symbol=symbol, trade_ts=trade_ts, window=window, prices=prices, complete=complete,
                peers=peers, facts=builder.result.by_key(), missing=builder.result.missing,
            )
        except Exception:  # noqa: BLE001 - 报告失败时仍然给出数据表
            logger.exception("stock report failed for %s", symbol)
    return builder.result


def _basic(builder: _Builder, repository: Any, last: pd.Series, trade_ts: pd.Timestamp) -> None:
    list_date = last.get("list_date")
    if list_date is not None and not pd.isna(list_date):
        listed = pd.Timestamp(list_date).date()
        years = (trade_ts.date() - listed).days / 365.25
        span = f"上市 {years:.0f} 年" if years >= 1 else f"上市不到一年（{(trade_ts.date() - listed).days} 天）"
        builder.add("list_date", "基本信息", "上市日期", f"{listed}（{span}）", years)
    st = last.get("is_st") is True or last.get("is_st") == 1
    builder.add("is_st", "基本信息", "是否 ST", "是（有退市风险警示）" if st else "否", 1.0 if st else 0.0)

    constituents = repository.read_table("index_constituents")
    found = False
    inside: list[str] = []
    since = ""
    for index_symbol, (label, _) in INDEX_UNIVERSES.items():
        lists = stored_lists(constituents, index_symbol)
        if not lists:
            continue
        members = members_on(lists, trade_ts.date())
        if members is None:
            continue
        found = True
        since = max(since, max(day for day in lists if day <= trade_ts.date()).isoformat())
        if builder.result.symbol in members:
            inside.append(label)
    if not found:
        builder.lack("指数成分股", "平台还没有指数成分股名单。")
    else:
        labels = "、".join(label for label, _ in INDEX_UNIVERSES.values())
        text = "、".join(inside) if inside else f"不在 {labels} 中"
        builder.add("indexes", "基本信息", "所属指数", text, float(len(inside)), since)


def _trend(builder: _Builder, series: pd.Series, last: pd.Series) -> None:
    close, pre = last.get("raw_close"), last.get("pre_close")
    if _finite(close):
        builder.add("close", "价格走势", "收盘价", f"{float(close):.2f} 元", float(close))
    if _finite(close) and _finite(pre) and float(pre) > 0:
        change = float(close) / float(pre) - 1
        flag = ""
        if _finite(last.get("up_limit")) and float(close) >= float(last["up_limit"]) - 0.005:
            flag = "（涨停）"
        elif _finite(last.get("down_limit")) and float(close) <= float(last["down_limit"]) + 0.005:
            flag = "（跌停）"
        builder.add("change_1d", "价格走势", "当日涨跌幅", _signed(change) + flag, change)
    if series.empty:
        return
    price = float(series.iloc[-1])
    for n in (5, 20, 60, 250):
        if len(series) > n and float(series.iloc[-1 - n]) > 0:
            value = price / float(series.iloc[-1 - n]) - 1
            builder.add(f"ret_{n}d", "价格走势", f"近 {n} 个交易日涨跌幅", _signed(value), value)
    year = series.iloc[-250:]
    if len(year) >= 120:
        high, low = float(year.max()), float(year.min())
        builder.add("from_high_250d", "价格走势", "距近一年最高价", _signed(price / high - 1), price / high - 1)
        builder.add("from_low_250d", "价格走势", "距近一年最低价", _signed(price / low - 1), price / low - 1)
        drawdown = float((year / year.cummax() - 1).min())
        builder.add("max_drawdown_250d", "价格走势", "近一年最大回撤", _signed(drawdown), drawdown)
    for n in (20, 60):
        if len(series) >= n:
            gap = price / float(series.iloc[-n:].mean()) - 1
            side = "上方" if gap >= 0 else "下方"
            builder.add(f"ma{n}_gap", "价格走势", f"收盘价相对 {n} 日均线", f"在均线{side} {abs(gap) * 100:.1f}%", gap)
    if len(series) >= 15:
        diffs = series.iloc[-15:].diff().dropna()
        gains, losses = float(diffs.clip(lower=0).mean()), float((-diffs).clip(lower=0).mean())
        rsi = 100.0 if losses == 0 else 100 - 100 / (1 + gains / losses)
        builder.add("rsi_14", "价格走势", "14 日 RSI（70 以上偏热，30 以下偏冷）", f"{rsi:.0f}", rsi)
    returns = series.pct_change().iloc[-60:].dropna()
    if len(returns) >= 40:
        vol = float(returns.std() * math.sqrt(252))
        builder.add("volatility_60d", "价格走势", "近 60 日年化波动率", _plain(vol), vol)


def _trading(builder: _Builder, amounts: pd.Series, last: pd.Series) -> None:
    recent = amounts.iloc[-20:].dropna()
    if len(recent) >= 10:
        average = float(recent.mean())
        builder.add("amount_20d", "成交", "近 20 日平均成交额", _yi(average), average)
        if _finite(last.get("amount")) and average > 0:
            ratio = float(last["amount"]) / average
            builder.add("amount_ratio", "成交", "当日成交额 / 近 20 日平均", f"{ratio:.1f} 倍", ratio)


def _industry(builder: _Builder, repository: Any, symbol: str, symbols: list[str], trade_ts: pd.Timestamp) -> list[str]:
    exposures = repository.read_table(EXPOSURES_TABLE)
    if exposures.empty:
        builder.lack("行业", "平台还没有行业分类。")
        return []
    days = pd.DataFrame({"symbol": symbols, "date": trade_ts})
    codes = industry_on(days, exposures).set_axis(symbols)
    own = codes.get(symbol)
    if own is None or pd.isna(own):
        builder.lack("行业", "这只股票还没有行业分类记录。")
        return []
    peers = [peer for peer, code in codes.items() if code == own]
    changed = exposures[(exposures["symbol"] == symbol) & (pd.to_datetime(exposures["date"]) <= trade_ts)]
    as_of = pd.Timestamp(changed["date"].max()).date().isoformat() if not changed.empty else ""
    builder.add("industry", "基本信息", "行业（证监会分类）", f"{industry_name(own)}（同行业 {len(peers)} 只）", float(len(peers)), as_of)
    return peers


def _compare(builder: _Builder, prices: pd.DataFrame, amounts: pd.DataFrame, symbol: str, peers: list[str]) -> None:
    def add(key: str, label: str, values: pd.Series, word: str, minimum: int = MIN_MARKET, scope: str = "全市场") -> None:
        found = _position(values, symbol, minimum)
        if found is not None:
            share, count = found
            builder.add(key, "全市场比较", label, f"{word}{scope} {share * 100:.0f}% 的股票（共 {count} 只）", share)

    latest = prices.iloc[-1]
    for n in (20, 250):
        if len(prices) > n:
            add(f"rank_ret_{n}d", f"近 {n} 个交易日涨幅在全市场的位置", latest / prices.iloc[-1 - n] - 1, "高于")
    returns = prices.pct_change().iloc[-60:]
    if len(returns) >= 40:
        vol = returns.std().where(returns.count() >= 40) * math.sqrt(252)
        add("rank_volatility_60d", "波动率在全市场的位置", vol, "高于")
    recent = amounts.iloc[-20:]
    add("rank_amount_20d", "成交额在全市场的位置", recent.mean().where(recent.count() >= 10), "高于")
    if len(peers) >= MIN_PEERS and len(prices) > 20:
        own_peers = [peer for peer in peers if peer in prices.columns]
        changes = latest[own_peers] / prices.iloc[-21][own_peers] - 1
        add("industry_rank_ret_20d", "近 20 个交易日涨幅在同行业的位置", changes, "高于", MIN_PEERS, "同行业")


def _valuation(builder: _Builder, repository: Any, symbol: str, trade_ts: pd.Timestamp, peers: list[str]) -> None:
    start = (trade_ts - pd.DateOffset(years=VALUATION_YEARS)).date()
    history = repository.get_daily_indicators([symbol], start, trade_ts.date())
    today = history[history["trade_date"] == trade_ts]
    if today.empty or today.drop(columns=["symbol", "trade_date"]).isna().all(axis=None):
        builder.lack("估值", "平台还没有这只股票的估值与换手率。")
        return
    row = today.iloc[-1]
    pe = row.get("pe_ttm")
    if _finite(pe):
        pe = float(pe)
        text = f"{pe:.1f}" if pe > 0 else "为负（最近四个季度亏损）"
        builder.add("pe_ttm", "估值", "市盈率（TTM）", text, pe)
        past = history["pe_ttm"].dropna()
        past = past[past > 0]
        if pe > 0 and len(past) >= 250:
            years = (trade_ts - history.loc[past.index, "trade_date"].min()).days / 365.25
            share = float((past < pe).mean())
            builder.add("pe_position", "估值", f"市盈率在自身近 {years:.0f} 年中的位置（越低越便宜）",
                        f"高于自身 {share * 100:.0f}% 的交易日", share)
    for key, label in (("pb_mrq", "市净率"), ("ps_ttm", "市销率（TTM）")):
        if _finite(row.get(key)) and float(row[key]) > 0:
            builder.add(key, "估值", label, f"{float(row[key]):.2f}", float(row[key]))
    if _finite(row.get("turnover_rate")):
        builder.add("turnover_rate", "成交", "当日换手率", f"{float(row['turnover_rate']):.2f}%", float(row["turnover_rate"]))
    if _finite(pe) and pe > 0 and len(peers) >= MIN_PEERS:
        peer_pe = repository.get_daily_indicators(peers, trade_ts.date(), trade_ts.date(), columns=["pe_ttm"])["pe_ttm"]
        peer_pe = peer_pe[peer_pe > 0]
        if len(peer_pe) >= MIN_PEERS:
            median = float(peer_pe.median())
            builder.add("industry_pe_median", "估值", "同行业市盈率中位数", f"{median:.1f}（{len(peer_pe)} 只有数据）", median)


def report_in_force(reports: pd.DataFrame, trade_ts: pd.Timestamp) -> pd.Series | None:
    """The newest report already published on the day, under the rules of ``fundamentals.point_in_time``."""

    published = reports.dropna(subset=["pub_date"]).copy()
    if published.empty:
        return None
    published["pub_date"] = pd.to_datetime(published["pub_date"])
    published["stat_date"] = pd.to_datetime(published["stat_date"])
    published = published[published["pub_date"] <= trade_ts].sort_values(["pub_date", "stat_date"])
    if published.empty:
        return None
    published = published[published["stat_date"] >= published["stat_date"].cummax()]
    report = published.iloc[-1]
    if (trade_ts - report["pub_date"]).days > REPORT_MAX_AGE_DAYS:
        return None
    return report


def _financials(builder: _Builder, repository: Any, symbol: str, trade_ts: pd.Timestamp) -> None:
    report = report_in_force(repository.get_fundamentals([symbol]), trade_ts)
    if report is None:
        builder.lack("财务", "平台还没有这只股票当时已公告的财报。")
        return
    stat, pub = report["stat_date"].date(), report["pub_date"].date()
    period = f"{stat.year} 年{REPORT_NAMES.get(stat.month, stat.isoformat())}"
    as_of = pub.isoformat()
    builder.add("report", "财务", "最新财报", f"{period}（{pub} 公告）", None, as_of)
    for key, label in (("roe_avg", "净资产收益率（年初至报告期）"), ("net_margin", "销售净利率"), ("gross_margin", "销售毛利率")):
        if _finite(report.get(key)):
            builder.add(key, "财务", label, _plain(float(report[key])), float(report[key]), as_of)
    growth = next((key for key in ("yoy_parent_net_profit", "yoy_net_profit") if _finite(report.get(key))), None)
    if growth:
        builder.add("profit_growth", "财务", "净利润同比增长", _signed(float(report[growth])), float(report[growth]), as_of)
    if _finite(report.get("asset_to_equity")) and float(report["asset_to_equity"]) > 0:
        debt = 1 - 1 / float(report["asset_to_equity"])
        builder.add("debt_ratio", "财务", "资产负债率", _plain(debt), debt, as_of)


def _events(builder: _Builder, repository: Any, symbol: str, trade_ts: pd.Timestamp) -> None:
    actions = repository.read_table("corporate_actions")
    if actions.empty:
        return
    actions = actions[actions["symbol"] == symbol].copy()
    actions["ex_date"] = pd.to_datetime(actions["ex_date"])
    recent = actions[(actions["ex_date"] <= trade_ts) & (actions["ex_date"] > trade_ts - pd.Timedelta(days=365))]
    if recent.empty:
        builder.add("last_action", "事件", "最近一年的分红送转", "没有记录", 0.0)
        return
    action = recent.sort_values("ex_date").iloc[-1]
    parts = []
    if _finite(action.get("cash_per_share")) and float(action["cash_per_share"]) > 0:
        parts.append(f"每 10 股派 {float(action['cash_per_share']) * 10:.2f} 元")
    if _finite(action.get("share_multiplier")) and float(action["share_multiplier"]) > 1:
        parts.append(f"每 10 股送转 {(float(action['share_multiplier']) - 1) * 10:.1f} 股")
    day = action["ex_date"].date().isoformat()
    builder.add("last_action", "事件", "最近一次除权除息", f"{day}，{'，'.join(parts) or '有记录'}", float(len(recent)), day)
