"""Every stock on the newest local day in one table, for the AI Q&A's ranking and comparison lookups.

One row per stock with a bar that day: price and size, valuation and turnover that day, returns
over 20 and 60 trading days, average turnover in money, the newest financial report in force,
the industry and the indexes it belongs to. Point in time like the rest of the AI researcher:
nothing after the day is read. The table is built once per data version and kept in memory.

Rankings only order stocks by one number. They say nothing about whether to buy anything, and
every ranking block says so.
"""

from __future__ import annotations

import math
import re
import threading
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pandas as pd

from quant_platform.ai_research.facts import industry_name
from quant_platform.ai_research.report import _data_stamp, _report_on, period_name
from quant_platform.data.index_constituents import INDEX_UNIVERSES, members_on, stored_lists
from quant_platform.data.industry import EXPOSURES_TABLE, industry_on


def _yi(x: float) -> str:
    return f"{x / 1e8:,.0f} 亿" if abs(x) >= 1e10 else f"{x / 1e8:,.1f} 亿"


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _signed(x: float) -> str:
    return f"{x * 100:+.1f}%"


# 可以排序、比较的指标：名称、格式、是否来自财报（来自财报的同时显示报告期）。
METRICS: dict[str, tuple[str, Callable[[float], str], bool]] = {
    "market_cap": ("总市值", _yi, False),
    "pe_ttm": ("市盈率（TTM）", lambda x: f"{x:.1f}", False),
    "pb_mrq": ("市净率", lambda x: f"{x:.2f}", False),
    "ps_ttm": ("市销率（TTM）", lambda x: f"{x:.2f}", False),
    "turnover_rate": ("当日换手率", lambda x: f"{x:.2f}%", False),
    "amount_20d": ("近 20 日平均成交额", _yi, False),
    "ret_20d": ("近 20 个交易日涨跌幅", _signed, False),
    "ret_60d": ("近 60 个交易日涨跌幅", _signed, False),
    "roe": ("净资产收益率（年初至报告期）", _pct, True),
    "gross_margin": ("毛利率", _pct, True),
    "net_margin": ("净利率", _pct, True),
    "profit_yoy": ("净利润同比", _signed, True),
    "debt_ratio": ("资产负债率", _pct, True),
}
# 估值为负（亏损、净资产为负）时没有可比性，排序时去掉。
POSITIVE_ONLY = {"pe_ttm", "pb_mrq", "ps_ttm"}
DEFAULT_COMPARE = ["market_cap", "pe_ttm", "pb_mrq", "roe", "gross_margin", "profit_yoy", "debt_ratio", "ret_60d"]
SCOPES = {key: (index_symbol, label) for index_symbol, (label, key) in INDEX_UNIVERSES.items()}
# 日常说法 -> 证监会行业分类名称（证监会的名称很长，和平时的叫法不一样）。
INDUSTRY_ALIASES: dict[str, tuple[str, ...]] = {
    "银行": ("货币金融服务",),
    "券商": ("资本市场服务",), "证券": ("资本市场服务",),
    "保险": ("保险业",),
    "金融": ("货币金融服务", "资本市场服务", "保险业", "其他金融业"),
    "白酒": ("酒、饮料和精制茶制造业",), "酒": ("酒、饮料和精制茶制造业",),
    "食品饮料": ("食品制造业", "酒、饮料和精制茶制造业"),
    "半导体": ("计算机、通信和其他电子设备制造业",), "芯片": ("计算机、通信和其他电子设备制造业",),
    "电子": ("计算机、通信和其他电子设备制造业",),
    "医药": ("医药制造业",), "生物医药": ("医药制造业",), "医疗": ("医药制造业", "专用设备制造业", "卫生"),
    "新能源": ("电气机械和器材制造业",), "光伏": ("电气机械和器材制造业",), "电池": ("电气机械和器材制造业",),
    "软件": ("软件和信息技术服务业",), "计算机": ("软件和信息技术服务业", "计算机、通信和其他电子设备制造业"),
    "互联网": ("互联网和相关服务",), "传媒": ("新闻和出版业", "广播、电视、电影和录音制作业", "互联网和相关服务"),
    "通信": ("计算机、通信和其他电子设备制造业", "电信、广播电视和卫星传输服务"),
    "汽车": ("汽车制造业",), "地产": ("房地产业",), "房地产": ("房地产业",),
    "电力": ("电力、热力生产和供应业",), "公用事业": ("电力、热力生产和供应业", "燃气生产和供应业", "水的生产和供应业"),
    "煤炭": ("煤炭开采和洗选业",), "石油": ("石油和天然气开采业", "石油、煤炭及其他燃料加工业"),
    "钢铁": ("黑色金属冶炼和压延加工业",), "有色": ("有色金属冶炼和压延加工业", "有色金属矿采选业"),
    "化工": ("化学原料和化学制品制造业", "化学纤维制造业"), "建材": ("非金属矿物制品业",),
    "军工": ("铁路、船舶、航空航天和其他运输设备制造业",), "航空": ("航空运输业",),
    "物流": ("道路运输业", "水上运输业", "多式联运和运输代理业", "装卸搬运和仓储业"),
    "建筑": ("土木工程建筑业", "房屋建筑业", "建筑装饰、装修和其他建筑业", "建筑安装业"),
    "机械": ("专用设备制造业", "通用设备制造业"), "家电": ("电气机械和器材制造业",),
    "农业": ("农业", "畜牧业", "渔业", "林业", "农副食品加工业"), "养殖": ("畜牧业", "渔业"),
    "纺织服装": ("纺织业", "纺织服装、服饰业"), "零售": ("零售业",), "环保": ("生态保护和环境治理业",),
}
MAX_RANK_ROWS = 20
RANK_NOTE = "只是按这一项指标排序，不代表买卖建议。"
HISTORY_CALENDAR_DAYS = 120

_CACHE: dict[str, tuple[str, pd.Timestamp, pd.DataFrame]] = {}
_LOCK = threading.Lock()


def _finite(x: Any) -> bool:
    try:
        return x is not None and not pd.isna(x) and math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def build_snapshot(repository: Any, names: dict[str, str]) -> tuple[pd.Timestamp, pd.DataFrame]:
    """``(day, table)``: one row per stock with a bar on the newest local day, indexed by symbol."""

    bounds = repository.daily_bar_bounds()
    if bounds is None:
        raise ValueError("平台还没有行情数据。")
    newest = bounds[1]
    window = repository.get_daily_bars(start_date=newest - timedelta(days=HISTORY_CALENDAR_DAYS), end_date=newest)
    trade_ts = pd.Timestamp(window["trade_date"].max()).normalize()
    today = window[window["trade_date"] == trade_ts].drop_duplicates("symbol", keep="last").set_index("symbol")
    symbols = list(today.index)
    prices = window.pivot_table(index="trade_date", columns="symbol", values="adjusted_close", aggfunc="last").sort_index()
    amounts = window.pivot_table(index="trade_date", columns="symbol", values="amount", aggfunc="last").sort_index()
    table = pd.DataFrame(index=pd.Index(symbols, name="symbol"))
    table["name"] = [names.get(symbol) or names.get(symbol.split(".")[0]) or symbol for symbol in symbols]
    table["close"] = pd.to_numeric(today["raw_close"], errors="coerce")
    table["is_st"] = today["is_st"].astype("boolean").fillna(False).astype(bool) if "is_st" in today else False
    for days in (20, 60):
        table[f"ret_{days}d"] = (prices.iloc[-1] / prices.iloc[-days - 1] - 1).reindex(symbols) if len(prices) > days else float("nan")
    table["amount_20d"] = amounts.iloc[-20:].mean().where(amounts.iloc[-20:].count() >= 10).reindex(symbols)

    indicators = repository.get_daily_indicators(None, trade_ts.date(), trade_ts.date(), columns=["pe_ttm", "pb_mrq", "ps_ttm", "turnover_rate"])
    indicators = indicators.drop_duplicates("symbol", keep="last").set_index("symbol") if not indicators.empty else pd.DataFrame()
    for column in ("pe_ttm", "pb_mrq", "ps_ttm", "turnover_rate"):
        table[column] = pd.to_numeric(indicators[column], errors="coerce").reindex(symbols) if column in indicators else float("nan")

    reports = _report_on(repository.get_fundamentals(), trade_ts)
    def report(column: str) -> pd.Series:
        return pd.to_numeric(reports[column], errors="coerce").reindex(symbols) if column in reports else pd.Series(float("nan"), index=symbols)
    growth = report("yoy_parent_net_profit").fillna(report("yoy_net_profit"))
    leverage = report("asset_to_equity")
    table["roe"], table["gross_margin"], table["net_margin"], table["profit_yoy"] = (
        report("roe_avg"), report("gross_margin"), report("net_margin"), growth)
    table["debt_ratio"] = (1 - 1 / leverage).where(leverage > 0)
    table["market_cap"] = table["close"] * report("total_shares")
    table["report_period"] = (reports["stat_date"].reindex(symbols).map(lambda d: period_name(pd.Timestamp(d)) if pd.notna(d) else "")
                              if "stat_date" in reports else "")

    exposures = repository.read_table(EXPOSURES_TABLE)
    if not exposures.empty:
        codes = industry_on(pd.DataFrame({"symbol": symbols, "date": trade_ts}), exposures).set_axis(symbols)
        table["industry_code"] = codes
        table["industry"] = codes.map(lambda code: industry_name(code) if isinstance(code, str) else "")
    else:
        table["industry_code"], table["industry"] = None, ""
    constituents = repository.read_table("index_constituents")
    table["indexes"] = [[] for _ in symbols]
    for key, (index_symbol, label) in SCOPES.items():
        members = members_on(stored_lists(constituents, index_symbol), trade_ts.date()) if not constituents.empty else None
        table[key] = table.index.isin(members or [])
        for symbol in members or []:
            if symbol in table.index:
                table.at[symbol, "indexes"].append(label)
    return trade_ts, table


def snapshot(repository: Any, names: dict[str, str]) -> tuple[pd.Timestamp, pd.DataFrame]:
    """:func:`build_snapshot`, rebuilt only when a local data file changes."""

    root = getattr(repository, "root", None)
    if root is None:                      # 没有数据目录（例如测试用的假仓库）：每次现算
        return build_snapshot(repository, names)
    key, stamp = str(root), _data_stamp(root)
    with _LOCK:
        cached = _CACHE.get(key)
        if cached and cached[0] == stamp:
            return cached[1], cached[2]
    day, table = build_snapshot(repository, names)
    with _LOCK:
        _CACHE[key] = (stamp, day, table)
    return day, table


def _text(metric: str, value: Any) -> str:
    return METRICS[metric][1](float(value)) if _finite(value) else "—"


def _bigrams(word: str) -> set[str]:
    word = re.sub(r"[\s、，,和与及业类行]+", "", word)
    return {word[i:i + 2] for i in range(len(word) - 1)} or ({word} if word else set())


def match_industries(table: pd.DataFrame, keyword: str) -> list[str]:
    """Industry names that contain the keyword or share a two-character piece with it (证监会行业名称很长)."""

    keyword = keyword.strip().removesuffix("行业").removesuffix("板块")
    names = {name for name in table["industry"].dropna() if name}
    if keyword in INDUSTRY_ALIASES:
        return sorted(names & set(INDUSTRY_ALIASES[keyword]))
    found = sorted({name for name in names if keyword in name})
    if found or not keyword:
        return found
    pieces = _bigrams(keyword)
    return sorted({name for name in names if any(piece in name for piece in pieces)})


def rank(table: pd.DataFrame, day: pd.Timestamp, metric: str, *, order: str = "high", scope: str = "all",
         industry: str = "", industry_of: str | None = None, limit: int = 10) -> dict[str, Any]:
    """The top ``limit`` stocks by ``metric`` within a scope, as a data block for the Q&A."""

    if metric not in METRICS:
        raise ValueError(f"不能按“{metric}”排序。可以用：{'、'.join(label for label, _, _ in METRICS.values())}")
    label, _, from_report = METRICS[metric]
    notes = ["已去掉 ST 股票。"]
    rows = table[~table["is_st"]]
    title_scope = "全市场"
    if scope in SCOPES:
        rows = rows[rows[scope]]
        title_scope = SCOPES[scope][1]
    if industry_of:
        code = table.at[industry_of, "industry_code"] if industry_of in table.index else None
        if not isinstance(code, str):
            raise ValueError("这只股票没有行业分类，不能按它的行业筛选。")
        rows = rows[rows["industry_code"].map(lambda value: isinstance(value, str) and value == code)]
        title_scope += f" · {table.at[industry_of, 'industry']}"
    elif industry:
        matched = match_industries(table, industry)
        if not matched:
            raise ValueError(f"证监会行业分类里没有和“{industry}”相近的行业。")
        rows = rows[rows["industry"].isin(matched)]
        title_scope += f" · {'、'.join(matched)}"
        if len(matched) > 1 or industry not in matched[0]:
            notes.append(f"按证监会行业分类，“{industry}”对应：{'、'.join(matched)}。")
    values = pd.to_numeric(rows[metric], errors="coerce")
    missing = int(values.isna().sum())
    values = values.dropna()
    if metric in POSITIVE_ONLY:
        dropped = int((values <= 0).sum())
        values = values[values > 0]
        if dropped:
            notes.append(f"{label}为负的 {dropped} 只（亏损或净资产为负）没有可比性，没有排进来。")
    if missing:
        notes.append(f"{missing} 只没有这项数据，没有排进来。")
    if metric == "profit_yoy":
        notes.append("同比增长受去年同期基数影响很大：去年利润很小或为负时，会出现很极端的数字。")
    limit = max(1, min(int(limit or 10), MAX_RANK_ROWS))
    chosen = values.sort_values(ascending=order == "low").head(limit)
    columns = ["排名", "股票", "代码", label, "行业"] + (["报告期"] if from_report else []) + (["总市值"] if metric != "market_cap" else [])
    out = []
    for place, (symbol, value) in enumerate(chosen.items(), start=1):
        row = table.loc[symbol]
        line = [str(place), str(row["name"]), symbol.split(".")[0], _text(metric, value), str(row["industry"] or "—")]
        if from_report:
            line.append(str(row["report_period"] or "—"))
        if metric != "market_cap":
            line.append(_text("market_cap", row["market_cap"]))
        out.append(line)
    word = "最低" if order == "low" else "最高"
    notes.append(RANK_NOTE)
    return {"kind": "rank", "title": f"{title_scope}{label}{word}的 {len(out)} 只", "as_of": day.date().isoformat(),
            "columns": columns, "rows": out, "notes": notes, "symbols": [s.split(".")[0] for s in chosen.index],
            "count": int(len(values))}


def compare(table: pd.DataFrame, day: pd.Timestamp, symbols: list[str], metrics: list[str] | None = None) -> dict[str, Any]:
    """Several stocks side by side on the chosen metrics, as a data block for the Q&A."""

    metrics = [m for m in (metrics or DEFAULT_COMPARE) if m in METRICS] or DEFAULT_COMPARE
    found = [symbol for symbol in symbols if symbol in table.index]
    notes = []
    absent = [symbol for symbol in symbols if symbol not in table.index]
    if absent:
        notes.append(f"{'、'.join(s.split('.')[0] for s in absent)} 在 {day.date()} 没有行情（停牌、退市或还没上市），没有列出。")
    columns = ["股票", "代码"] + [METRICS[m][0] for m in metrics] + ["行业", "报告期"]
    rows = [[str(table.at[s, "name"]), s.split(".")[0], *[_text(m, table.at[s, m]) for m in metrics],
             str(table.at[s, "industry"] or "—"), str(table.at[s, "report_period"] or "—")] for s in found]
    if any(METRICS[m][2] for m in metrics):
        notes.append("财务指标来自各自最新公布的财报；净资产收益率是年初至报告期累计的，报告期不同时不能直接比较。")
    return {"kind": "compare", "title": f"{'、'.join(str(table.at[s, 'name']) for s in found) or '没有可比较的股票'}",
            "as_of": day.date().isoformat(), "columns": columns, "rows": rows, "notes": notes,
            "symbols": [s.split(".")[0] for s in found]}
