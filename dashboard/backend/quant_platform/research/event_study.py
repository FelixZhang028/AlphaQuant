"""Event study: what usually happened after a condition, across many stocks, next to all days.

The user picks up to three conditions (a 20-day fall of more than 20%, a close above the 60-day
average, a price-to-earnings ratio below 15 ...). Every stock and every day in the chosen range
and universe where all of them hold is an *event*. For each event the change over the following
5, 20 and 60 trading days is measured, and the same is measured for *all* eligible stock-days, so
the event can be told apart from what the market did anyway.

Rules, so the numbers can be trusted:

- Point in time: a condition on a day only uses that day's and earlier data (reports from their
  publication day, index lists in force that day).
- Changes run from the close of the event day to the close N trading days later, on adjusted
  prices, without trading costs. Excess change is against the average of all eligible stocks on
  the same day.
- One stock that keeps meeting the condition counts once per cooling-off period (by default the
  20 trading days being measured), so one episode is not counted twenty times.
- Suspended days, ST stocks (unless kept) and stocks listed for less than 60 trading days are left
  out. Events whose stock left the market before the horizon ended are counted as such, not
  silently dropped.

The result describes history. It is not a forecast for any stock and not advice to trade.
"""

from __future__ import annotations

import copy
import json
import logging
import math
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_platform.data.fundamentals import FUNDAMENTALS_TABLE, point_in_time
from quant_platform.data.index_constituents import INDEX_UNIVERSES, membership
from quant_platform.data.industry import EXPOSURES_TABLE

HORIZONS = (5, 20, 60)
MAIN_HORIZON = 20
MIN_LISTED_DAYS = 60
MAX_CONDITIONS = 3
FEW_EVENTS = 30
YEAR_WINDOW = 250
LOOKBACK_CALENDAR_DAYS = 420
RECENT_EVENTS = 20
COOLDOWNS = (0, 5, 20, 60)
BINS = [-math.inf, -0.3, -0.2, -0.1, -0.05, 0.0, 0.05, 0.1, 0.2, 0.3, math.inf]
BIN_LABELS = ["跌 30% 以上", "跌 20～30%", "跌 10～20%", "跌 5～10%", "跌 0～5%", "涨 0～5%", "涨 5～10%",
              "涨 10～20%", "涨 20～30%", "涨 30% 以上"]
SCOPES = {"all": "全市场", **{key: label for _, (label, key) in INDEX_UNIVERSES.items()}, "pool": "我的股票池"}
# 走势图上画的点：出现以后第几个交易日（必须包含 HORIZONS，这几天用精确值）。
PATH_DAYS = (*range(1, 11), 12, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60)
PATH_SAMPLE = 300_000          # “平时”的走势抽这么多个股票交易日，误差远小于 0.1%
MARKET_CELLS = 3_000_000       # “同一天全部股票”的走势：有事件的日子 × 股票，最多看这么多格
CACHE_SIZE = 64

logger = logging.getLogger(__name__)

# 页面上的“常见问题”：点一下就用默认设置（全市场、默认日期、冷却 20 天）统计。
PRESETS = (
    ("drop", "大跌之后会反弹吗？", "近 20 个交易日跌了 20% 以上", [{"type": "ret", "days": 20, "op": "<=", "value": -20}]),
    ("limit_up", "涨停以后呢？", "当天涨停", [{"type": "limit", "direction": "up"}]),
    ("limit_down", "跌停以后呢？", "当天跌停", [{"type": "limit", "direction": "down"}]),
    ("cross_up", "站上 60 日均线以后", "收盘价从下往上穿过 60 日均线", [{"type": "ma_cross", "days": 60, "direction": "up"}]),
    ("cross_down", "跌破 60 日均线以后", "收盘价从上往下穿过 60 日均线", [{"type": "ma_cross", "days": 60, "direction": "down"}]),
    ("volume", "突然放量以后", "成交额是近 20 日平均的 3 倍以上", [{"type": "amount_ratio", "op": ">=", "value": 3}]),
    ("half", "离一年高点跌了一半", "比近一年最高价低 50% 以上", [{"type": "from_high", "op": "<=", "value": -50}]),
    ("cheap", "市盈率很低的时候", "市盈率不到 10（只算盈利的公司）", [{"type": "pe", "op": "<=", "value": 10}]),
)


class EventStudyError(ValueError):
    """A request the user can fix; the message is shown as-is."""


# --------------------------------------------------------------------------- #
# 条件
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ConditionKind:
    label: str
    group: str
    unit: str = ""                    # "%" 表示页面上按百分数填写
    days: tuple[int, ...] = ()
    directions: tuple[tuple[str, str], ...] = ()   # (取值, 说法)
    compare: bool = True              # 要不要选 ≤ / ≥ 和数值
    source: str = "price"             # price / indicator / report
    minimum: float = -1e9
    maximum: float = 1e9
    example: float = 0.0


CONDITIONS: dict[str, ConditionKind] = {
    "ret": ConditionKind("近 N 个交易日涨跌幅", "价格", "%", (5, 20, 60), example=-20, minimum=-100, maximum=1000),
    "from_high": ConditionKind("距近一年最高价", "价格", "%", example=-30, minimum=-100, maximum=0),
    "from_low": ConditionKind("距近一年最低价", "价格", "%", example=50, minimum=0, maximum=10000),
    "ma_gap": ConditionKind("收盘价相对 N 日均线", "价格", "%", (20, 60), example=-10, minimum=-100, maximum=1000),
    "ma_cross": ConditionKind("收盘价当天穿过 N 日均线", "价格", days=(20, 60), compare=False,
                              directions=(("up", "从下往上穿过"), ("down", "从上往下穿过"))),
    "limit": ConditionKind("当天涨停或跌停", "价格", compare=False, directions=(("up", "涨停"), ("down", "跌停"))),
    "amount_ratio": ConditionKind("当日成交额 / 近 20 日平均", "成交", "倍", example=3, minimum=0, maximum=1000),
    "turnover": ConditionKind("当日换手率", "成交", "%", source="indicator", example=10, minimum=0, maximum=100),
    "pe": ConditionKind("市盈率（TTM，只算盈利的公司）", "估值", source="indicator", example=15, minimum=0, maximum=10000),
    "pb": ConditionKind("市净率", "估值", source="indicator", example=1, minimum=0, maximum=1000),
    "profit_yoy": ConditionKind("最新财报的净利润同比", "财务", "%", source="report", example=50, minimum=-10000, maximum=100000),
    "roe": ConditionKind("最新财报的净资产收益率（年初至报告期）", "财务", "%", source="report", example=10, minimum=-1000, maximum=1000),
}
OPS = {"<=": "≤", ">=": "≥"}


def _number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise EventStudyError("条件里的数值要填数字") from None
    if not math.isfinite(number):
        raise EventStudyError("条件里的数值要填数字")
    return number


def clean_condition(raw: dict[str, Any]) -> dict[str, Any]:
    """One condition as used (validated), with the sentence shown to the user."""

    if not isinstance(raw, dict) or raw.get("type") not in CONDITIONS:
        raise EventStudyError("有一个条件的种类不认识")
    kind = CONDITIONS[raw["type"]]
    out: dict[str, Any] = {"type": raw["type"]}
    label = kind.label
    if kind.days:
        days = int(_number(raw.get("days", kind.days[0])))
        if days not in kind.days:
            raise EventStudyError(f"{kind.label}的天数只能是 {'、'.join(map(str, kind.days))}")
        out["days"] = days
        label = label.replace("N", str(days))
    if kind.directions:
        direction = raw.get("direction") or kind.directions[0][0]
        words = dict(kind.directions)
        if direction not in words:
            raise EventStudyError(f"{kind.label}的方向不认识")
        out["direction"] = direction
        label = label.replace("穿过", words[direction]) if kind.days else f"当天{words[direction]}"
    if kind.compare:
        op = raw.get("op", "<=")
        if op not in OPS:
            raise EventStudyError("比较方式只能是 ≤ 或 ≥")
        value = _number(raw.get("value", kind.example))
        if not kind.minimum <= value <= kind.maximum:
            raise EventStudyError(f"{label}的数值要在 {kind.minimum:g} 到 {kind.maximum:g} 之间")
        out.update(op=op, value=value)
        label = f"{label} {OPS[op]} {value:g}{kind.unit}"
    out["label"] = label
    out["source"] = kind.source
    return out


def options() -> dict[str, Any]:
    """Everything the page needs to build its form."""

    return {
        "conditions": [{"type": key, "label": kind.label, "group": kind.group, "unit": kind.unit, "days": list(kind.days),
                        "directions": [{"value": v, "label": w} for v, w in kind.directions], "compare": kind.compare,
                        "example": kind.example, "source": kind.source} for key, kind in CONDITIONS.items()],
        "scopes": [{"value": key, "label": label} for key, label in SCOPES.items()],
        "horizons": list(HORIZONS), "main_horizon": MAIN_HORIZON, "cooldowns": list(COOLDOWNS),
        "max_conditions": MAX_CONDITIONS,
        "presets": [{"key": key, "question": question, "hint": hint, "conditions": conditions}
                    for key, question, hint, conditions in PRESETS],
    }


# --------------------------------------------------------------------------- #
# 行情面板：日期 × 股票，同一份数据版本只读一次
# --------------------------------------------------------------------------- #


@dataclass
class Panel:
    dates: pd.DatetimeIndex
    symbols: pd.Index
    close: pd.DataFrame          # 复权收盘价，停牌日沿用前一天
    has_bar: pd.DataFrame        # 这一天有没有行情
    trading: pd.DataFrame        # 有行情且没有停牌
    st: pd.DataFrame
    amount: pd.DataFrame
    limit_up: pd.DataFrame
    limit_down: pd.DataFrame
    listed: pd.DataFrame         # 到这一天为止已经有 MIN_LISTED_DAYS 个交易日的行情
    last_position: pd.Series     # 每只股票最后一根行情在日期里的位置


_PANELS: dict[str, tuple[str, Panel]] = {}
# 建面板要十几秒、占不少内存：同一时间只建一份，别的请求等它建好直接用。
_PANEL_LOCK = threading.Lock()


def _wide(frame: pd.DataFrame, column: str, dates: pd.DatetimeIndex, symbols: pd.Index) -> pd.DataFrame:
    return frame[column].unstack("symbol").reindex(index=dates, columns=symbols)


def build_panel(repository: Any, start: date | None = None) -> Panel:
    bounds = repository.daily_bar_bounds()
    if bounds is None:
        raise EventStudyError("平台还没有行情数据。")
    columns = ["symbol", "trade_date", "adjusted_close", "raw_close", "amount", "is_st", "is_suspended", "up_limit", "down_limit"]
    bars = repository._read_range("daily_bars", start_date=start, end_date=bounds[1], columns=columns)
    bars["trade_date"] = pd.to_datetime(bars["trade_date"]).dt.normalize()
    bars = bars.drop_duplicates(["trade_date", "symbol"], keep="last").set_index(["trade_date", "symbol"]).sort_index()
    dates = bars.index.get_level_values(0).unique().sort_values()
    symbols = bars.index.get_level_values(1).unique().sort_values()
    close = _wide(bars, "adjusted_close", dates, symbols).astype("float32")
    has_bar = close.notna()
    suspended = _wide(bars, "is_suspended", dates, symbols).astype("boolean").fillna(False).astype(bool)
    raw = _wide(bars, "raw_close", dates, symbols).astype("float64")
    up = _wide(bars, "up_limit", dates, symbols).astype("float64")
    down = _wide(bars, "down_limit", dates, symbols).astype("float64")
    positions = pd.Series(np.arange(len(dates)), index=dates)
    last = has_bar.apply(lambda col: positions[col].max() if col.any() else -1)
    return Panel(
        dates=dates, symbols=symbols, close=close.ffill(), has_bar=has_bar, trading=has_bar & ~suspended,
        st=_wide(bars, "is_st", dates, symbols).astype("boolean").fillna(False).astype(bool),
        amount=_wide(bars, "amount", dates, symbols).astype("float32"),
        limit_up=(raw - up).abs() < 0.005, limit_down=(raw - down).abs() < 0.005,
        listed=has_bar.cumsum() >= MIN_LISTED_DAYS, last_position=last,
    )


def panel(repository: Any) -> Panel:
    """The panel for the current version of the daily bars (rebuilt when a daily-bar file changes)."""

    root = getattr(repository, "root", None)
    if root is None:
        return build_panel(repository)
    # 面板只用日线：下载估值、财报时不用重建（那些数据每次统计时现读）。
    stamp = _stamp(repository)[1]
    with _PANEL_LOCK:
        cached = _PANELS.get(str(root))
        if cached and cached[0] == stamp:
            return cached[1]
        _PANELS.clear()                 # 只留一份，面板比较大：先放掉旧的再建
        built = build_panel(repository)
        _PANELS[str(root)] = (stamp, built)
        return built


def _stamp(repository: Any, tables: tuple[str, ...] = ()) -> tuple[str, str] | None:
    """The version of the daily bars and of ``tables``: changes when one of their files is written.

    Only the tables a question uses count, so a download of other data (which writes files all the
    time) does not throw away the panel and the remembered results."""

    root = getattr(repository, "root", None)
    if root is None:
        return None
    from quant_platform.ai_research.report import _data_stamp

    parts = []
    for table in ("daily_bars", *sorted(set(tables))):
        folder, file = Path(root) / table, Path(root) / f"{table}.parquet"
        if folder.is_dir():
            parts.append(_data_stamp(folder))
        elif file.exists():
            parts.append(f"{file.stat().st_mtime_ns}:{file.stat().st_size}")
        elif table == "daily_bars":
            parts.append(_data_stamp(root))          # 不认识的存放方式：退回看整个数据目录
        else:
            parts.append("-")
    return str(root), "|".join(parts)


def _tables(conditions: list[dict[str, Any]], scope: str, industries: list[str]) -> tuple[str, ...]:
    """Besides the daily bars, the tables a question reads."""

    tables = {"daily_indicators" if c["source"] == "indicator" else FUNDAMENTALS_TABLE
              for c in conditions if c["source"] != "price"}
    if scope not in ("all", "pool"):
        tables.add("index_constituents")
    if industries:
        tables.add(EXPOSURES_TABLE)
    return tuple(sorted(tables))


# --------------------------------------------------------------------------- #
# 条件的取值
# --------------------------------------------------------------------------- #


def _indicator(repository: Any, p: Panel, column: str, start: date, end: date) -> pd.DataFrame:
    frame = repository.get_daily_indicators(None, start, end, columns=[column])
    if frame.empty:
        return pd.DataFrame(np.nan, index=p.dates, columns=p.symbols)
    frame = frame.drop_duplicates(["trade_date", "symbol"], keep="last").set_index(["trade_date", "symbol"])
    return pd.to_numeric(frame[column], errors="coerce").unstack("symbol").reindex(index=p.dates, columns=p.symbols)


def _report(repository: Any, p: Panel, column: str, cells: pd.DataFrame) -> pd.DataFrame:
    """Report values point in time, only for the stock-days that may become events."""

    stacked = cells.stack()
    days = stacked[stacked].index.to_frame(index=False, name=["trade_date", "symbol"])
    out = pd.DataFrame(np.nan, index=p.dates, columns=p.symbols)
    if days.empty:
        return out
    reports = repository.get_fundamentals()
    if column == "profit_yoy" and not reports.empty:
        growth = pd.to_numeric(reports.get("yoy_parent_net_profit"), errors="coerce")
        reports = reports.assign(profit_yoy=growth.fillna(pd.to_numeric(reports.get("yoy_net_profit"), errors="coerce")))
    if column == "roe" and not reports.empty:
        reports = reports.assign(roe=pd.to_numeric(reports.get("roe_avg"), errors="coerce"))
    if reports.empty or column not in reports:
        return out
    values = point_in_time(days, reports, [column])
    filled = values.set_index(["trade_date", "symbol"])[column].unstack("symbol")
    return filled.reindex(index=p.dates, columns=p.symbols)


def condition_mask(repository: Any, p: Panel, cond: dict[str, Any], cells: pd.DataFrame, start: date, end: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``(holds, known)``: where the condition holds, and where its data exists (for coverage)."""

    close = p.close
    kind = cond["type"]
    if kind == "ret":
        values = close / close.shift(cond["days"]) - 1
    elif kind == "from_high":
        values = close / close.rolling(YEAR_WINDOW, min_periods=120).max() - 1
    elif kind == "from_low":
        values = close / close.rolling(YEAR_WINDOW, min_periods=120).min() - 1
    elif kind in ("ma_gap", "ma_cross"):
        values = close / close.rolling(cond["days"], min_periods=cond["days"]).mean() - 1
        if kind == "ma_cross":
            before = values.shift(1)
            holds = (values > 0) & (before <= 0) if cond["direction"] == "up" else (values < 0) & (before >= 0)
            return holds.fillna(False), values.notna() & before.notna()
    elif kind == "limit":
        holds = p.limit_up if cond["direction"] == "up" else p.limit_down
        return holds, p.trading
    elif kind == "amount_ratio":
        values = p.amount / p.amount.rolling(20, min_periods=10).mean()
    elif kind == "turnover":
        values = _indicator(repository, p, "turnover_rate", start, end)
    elif kind in ("pe", "pb"):
        values = _indicator(repository, p, "pe_ttm" if kind == "pe" else "pb_mrq", start, end)
        values = values.where(values > 0)            # 亏损（市盈率为负）没有可比性
    else:
        values = _report(repository, p, kind, cells)
    scale = 100.0 if CONDITIONS[kind].unit == "%" and kind != "turnover" else 1.0
    threshold = cond["value"] / scale
    holds = values <= threshold if cond["op"] == "<=" else values >= threshold
    return holds.fillna(False) & values.notna(), values.notna()


# --------------------------------------------------------------------------- #
# 范围
# --------------------------------------------------------------------------- #


def universe_mask(repository: Any, p: Panel, scope: str, pool: list[str], industries: list[str]) -> pd.DataFrame:
    mask = pd.DataFrame(True, index=p.dates, columns=p.symbols)
    if scope == "pool":
        wanted = set(pool)
        mask.loc[:, ~p.symbols.isin(wanted)] = False
    elif scope != "all":
        index_symbol = next((symbol for symbol, (_, key) in INDEX_UNIVERSES.items() if key == scope), None)
        if index_symbol is None:
            raise EventStudyError("不认识这个股票范围")
        stays = membership(repository.read_table("index_constituents"), index_symbol)
        if stays.empty:
            raise EventStudyError(f"本地还没有{SCOPES[scope]}的历史成分股")
        inside = np.zeros(mask.shape, dtype=bool)
        columns = {symbol: i for i, symbol in enumerate(p.symbols)}
        for row in stays.itertuples(index=False):
            col = columns.get(row.symbol)
            if col is None:
                continue
            first = p.dates.searchsorted(pd.Timestamp(row.effective_from))
            last = len(p.dates) if pd.isna(row.effective_to) else p.dates.searchsorted(pd.Timestamp(row.effective_to))
            inside[first:last, col] = True
        mask = pd.DataFrame(inside, index=p.dates, columns=p.symbols)
    if industries:
        exposures = repository.read_table(EXPOSURES_TABLE)
        if exposures.empty:
            raise EventStudyError("本地还没有行业分类")
        from quant_platform.ai_research.facts import industry_name

        exposures = exposures.assign(date=pd.to_datetime(exposures["date"]).dt.normalize(),
                                     name=exposures["industry"].map(industry_name))
        exposures = exposures.drop_duplicates(["date", "symbol"], keep="last")
        names = exposures.set_index(["date", "symbol"])["name"].unstack("symbol")
        names = names.reindex(names.index.union(p.dates)).ffill().bfill().reindex(index=p.dates, columns=p.symbols)
        mask &= names.isin(industries)
    return mask


# --------------------------------------------------------------------------- #
# 统计
# --------------------------------------------------------------------------- #


def cool_down(events: np.ndarray, gap: int) -> np.ndarray:
    """Keep the first event of each stock and then only events at least ``gap`` days after the last kept one."""

    if gap <= 1:
        return events
    kept = np.zeros_like(events)
    for col in range(events.shape[1]):
        rows = np.flatnonzero(events[:, col])
        position = 0
        while position < len(rows):
            row = rows[position]
            kept[row, col] = True
            position = int(np.searchsorted(rows, row + gap))
    return kept


def _summary(values: np.ndarray) -> dict[str, Any]:
    values = values[np.isfinite(values)]
    if not len(values):
        return {"count": 0}
    quantiles = np.quantile(values, [0.1, 0.25, 0.5, 0.75, 0.9])
    return {"count": int(len(values)), "mean": float(values.mean()), "median": float(quantiles[2]),
            "up_share": float((values > 0).mean()), "p10": float(quantiles[0]), "p25": float(quantiles[1]),
            "p75": float(quantiles[3]), "p90": float(quantiles[4])}


def _histogram(values: np.ndarray) -> list[float]:
    values = values[np.isfinite(values)]
    if not len(values):
        return [0.0] * (len(BINS) - 1)
    counts, _ = np.histogram(np.clip(values, -10, 10), bins=[max(b, -10) if b < 0 else min(b, 10) for b in BINS])
    return [round(float(c) / len(values), 4) for c in counts]


def _row_mean(values: np.ndarray) -> np.ndarray:
    """Mean of each row ignoring NaN; NaN for a row with no numbers (the last days of the data).

    Not ``np.nanmean`` inside ``warnings.catch_warnings``: that is not safe with two threads
    (the common questions are worked out in the background while users ask their own)."""

    known = np.isfinite(values)
    counts = known.sum(axis=1)
    sums = np.where(known, values, 0).sum(axis=1, dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(counts > 0, sums / np.maximum(counts, 1), np.nan)


def _mean(values: np.ndarray) -> float | None:
    values = values[np.isfinite(values)]
    return round(float(values.mean()), 5) if len(values) else None


def _path(close: np.ndarray, base: np.ndarray, rows: np.ndarray, cols: np.ndarray, last: np.ndarray,
          horizons: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """Average change from the event day to each of the next ``PATH_DAYS`` trading days.

    ``events``: the events themselves (exact). ``market``: all stocks on the same days as the events,
    weighted like the events. ``all``: all eligible stock-days (a fixed sample). On ``HORIZONS`` the
    exact numbers of the summary are used, so the chart and the numbers above it agree."""

    n = len(close)
    rng = np.random.default_rng(0)
    base_rows, base_cols = np.nonzero(base)
    if len(base_rows) > PATH_SAMPLE:
        pick = rng.choice(len(base_rows), PATH_SAMPLE, replace=False)
        base_rows, base_cols = base_rows[pick], base_cols[pick]
    days, where = np.unique(rows, return_inverse=True)
    columns = np.arange(close.shape[1])
    if len(days) and len(days) * len(columns) > MARKET_CELLS:
        columns = np.sort(rng.choice(len(columns), max(1, MARKET_CELLS // len(days)), replace=False))
    day_close = close[np.ix_(days, columns)]
    day_base = base[np.ix_(days, columns)]

    def change(r: np.ndarray, c: np.ndarray, k: int) -> np.ndarray:
        values = close[np.minimum(r + k, n - 1), c] / close[r, c] - 1
        return np.where((r + k < n) & (r + k <= last[c]), values, np.nan)

    out: dict[str, list[float | None]] = {"days": [0], "events": [0.0], "market": [0.0], "all": [0.0]}
    for k in PATH_DAYS:
        out["days"].append(k)
        events = change(rows, cols, k)
        if k in horizons:
            summary = horizons[k]
            mean, excess = summary["events"].get("mean"), summary["excess"].get("mean")
            out["events"].append(mean)
            out["market"].append(None if mean is None or excess is None else round(mean - excess, 5))
            out["all"].append(summary["all"].get("mean"))
            continue
        out["events"].append(_mean(events))
        out["all"].append(_mean(change(base_rows, base_cols, k)))
        if not len(days):
            out["market"].append(None)
            continue
        ahead = close[np.ix_(np.minimum(days + k, n - 1), columns)] / day_close - 1
        usable = day_base & (days[:, None] + k < n) & (days[:, None] + k <= last[columns][None, :])
        day_mean = _row_mean(np.where(usable, ahead, np.nan))
        out["market"].append(_mean(np.where(np.isfinite(events), day_mean[where], np.nan)))
    for key in ("events", "market", "all"):
        out[key] = [None if v is None or not math.isfinite(v) else round(float(v), 5) for v in out[key]]
    return out


PRESET_TABLES = ("daily_indicators",)        # 常见问题里有市盈率
_RESULTS: OrderedDict[tuple, dict[str, Any]] = OrderedDict()
_RESULTS_LOCK = threading.Lock()
_WARMED: set[tuple[str, str]] = set()


def warm(repository: Any, names: dict[str, str]) -> None:
    """Work out the common questions once per data version, so clicking one answers at once."""

    stamp = _stamp(repository, PRESET_TABLES)
    with _RESULTS_LOCK:
        if stamp is None or stamp in _WARMED:
            return
        _WARMED.add(stamp)
    for _key, _question, _hint, conditions in PRESETS:
        try:
            run(repository, {"conditions": conditions}, pool=[], names=names)
        except Exception:  # noqa: BLE001 - 预先算不出来，用户点的时候再算
            logger.exception("event study preset %s failed", _key)


def warm_later(repository: Any, names: dict[str, str]) -> None:
    stamp = _stamp(repository, PRESET_TABLES)
    if stamp is None or stamp in _WARMED:
        return
    threading.Thread(target=warm, args=(repository, names), name="event-study-warm", daemon=True).start()


def run(repository: Any, request: dict[str, Any], *, pool: list[str], names: dict[str, str]) -> dict[str, Any]:
    conditions = [clean_condition(raw) for raw in (request.get("conditions") or [])]
    if not conditions:
        raise EventStudyError("请至少选一个条件")
    if len(conditions) > MAX_CONDITIONS:
        raise EventStudyError(f"最多同时用 {MAX_CONDITIONS} 个条件")
    scope = request.get("scope") or "all"
    if scope not in SCOPES:
        raise EventStudyError("不认识这个股票范围")
    if scope == "pool" and not pool:
        raise EventStudyError("你的股票池是空的")
    cooldown = int(request.get("cooldown", MAIN_HORIZON))
    if cooldown not in COOLDOWNS:
        raise EventStudyError("冷却期只能是 " + "、".join(map(str, COOLDOWNS)) + " 个交易日")
    industries = [str(name) for name in request.get("industries") or []][:5]
    keep_st = bool(request.get("keep_st", False))

    bounds = repository.daily_bar_bounds()
    if bounds is None:
        raise EventStudyError("平台还没有行情数据。")
    try:
        start = date.fromisoformat(str(request.get("start") or "")) if request.get("start") else bounds[0] + timedelta(days=LOOKBACK_CALENDAR_DAYS)
        end = date.fromisoformat(str(request.get("end") or "")) if request.get("end") else bounds[1]
    except ValueError:
        raise EventStudyError("日期格式不对") from None
    start, end = max(start, bounds[0]), min(end, bounds[1])
    if start >= end:
        raise EventStudyError("开始日期要早于结束日期")

    # 同一份数据、同样的问题，结果一样：记住最近的几十个（常见问题预先算好就是放在这里）。
    stamp = _stamp(repository, _tables(conditions, scope, industries))
    key = None if stamp is None else (stamp, json.dumps(
        {"conditions": [{k: v for k, v in c.items() if k != "label"} for c in conditions], "scope": scope,
         "cooldown": cooldown, "industries": industries, "keep_st": keep_st, "start": start.isoformat(),
         "end": end.isoformat(), "pool": sorted(pool) if scope == "pool" else []}, sort_keys=True, ensure_ascii=False))
    if key is not None:
        with _RESULTS_LOCK:
            if key in _RESULTS:
                _RESULTS.move_to_end(key)
                return copy.deepcopy(_RESULTS[key])
    result = _compute(repository, conditions, scope, pool, industries, cooldown, keep_st, start, end, names)
    if key is not None:
        with _RESULTS_LOCK:
            _RESULTS[key] = result
            while len(_RESULTS) > CACHE_SIZE:
                _RESULTS.popitem(last=False)
    return copy.deepcopy(result)


def _compute(repository: Any, conditions: list[dict[str, Any]], scope: str, pool: list[str], industries: list[str],
             cooldown: int, keep_st: bool, start: date, end: date, names: dict[str, str]) -> dict[str, Any]:
    p = panel(repository)
    in_range = pd.Series((p.dates >= pd.Timestamp(start)) & (p.dates <= pd.Timestamp(end)), index=p.dates)
    base = p.trading & p.listed
    if not keep_st:
        base &= ~p.st
    base &= universe_mask(repository, p, scope, pool, industries)
    base = base.mul(in_range, axis=0).astype(bool)

    holds = base.copy()
    coverage = []
    for cond in conditions:
        mask, known = condition_mask(repository, p, cond, holds, start, end)
        if cond["source"] != "price":
            # 估值和财务数据的历史比行情短：说清楚满足前面条件的股票交易日里，有多少有这项数据。
            candidates = holds.to_numpy()
            covered = known.to_numpy() & candidates
            years = p.dates.year.to_numpy()[np.nonzero(covered)[0]]
            coverage.append({"label": cond["label"], "share": round(float(covered.sum() / max(1, candidates.sum())), 4),
                             "since": int(years.min()) if len(years) else None})
        holds &= mask
    events = cool_down(holds.to_numpy(), cooldown)
    base_np = base.to_numpy()

    positions = np.arange(len(p.dates))[:, None]
    last = p.last_position.to_numpy()[None, :]
    close = p.close.to_numpy()
    horizons = {}
    for h in HORIZONS:
        future = np.full_like(close, np.nan)
        future[:-h] = close[h:]
        change = future / close - 1
        ended = positions + h > last                    # 之后退市（或停牌到数据结束）
        not_yet = positions + h >= len(p.dates)         # 还没到 h 个交易日
        change[ended | not_yet] = np.nan
        market = _row_mean(np.where(base_np, change, np.nan))[:, None]
        event_values = change[events]
        horizons[h] = {
            "events": _summary(event_values), "all": _summary(change[base_np]),
            "excess": _summary((change - market)[events]),
            "not_yet": int((events & not_yet).sum()), "left_market": int((events & ended & ~not_yet).sum()),
        }
        if h == MAIN_HORIZON:
            main_change, main_market = change, market
    rows, cols = np.nonzero(events)
    total = int(len(rows))
    years = p.dates.year.to_numpy()
    by_year = []
    for year in sorted(set(years[rows])) if total else []:
        in_year = years == year
        ev = main_change[rows[years[rows] == year], cols[years[rows] == year]]
        allv = main_change[in_year][base_np[in_year]]
        es, bs = _summary(ev), _summary(allv)
        by_year.append({"year": int(year), "events": int((years[rows] == year).sum()), "mean": es.get("mean"),
                        "up_share": es.get("up_share"), "all_mean": bs.get("mean"), "all_up_share": bs.get("up_share")})
    # 最近几次已经满 MAIN_HORIZON 个交易日的事件：是有结果的历史例子，不是“今天满足条件的股票”。
    finished = np.flatnonzero(np.isfinite(main_change[rows, cols])) if total else np.array([], dtype=int)
    order = finished[np.argsort(rows[finished])[::-1]][:RECENT_EVENTS]
    recent = []
    for i in order:
        symbol = str(p.symbols[cols[i]])
        value = main_change[rows[i], cols[i]]
        recent.append({"date": p.dates[rows[i]].date().isoformat(), "symbol": symbol.split(".")[0],
                       "name": names.get(symbol, symbol.split(".")[0]),
                       "change": None if not math.isfinite(value) else round(float(value), 4),
                       "excess": None if not math.isfinite(value) else round(float(value - main_market[rows[i], 0]), 4)})
    notes = ["从满足条件那天的收盘价算到之后第 N 个交易日的收盘价（复权），不含交易成本；超额是减去同一天全部股票的平均涨跌。",
             f"同一只股票满足条件后 {cooldown} 个交易日内不重复计算。" if cooldown > 1 else "同一只股票每天满足条件都算一次（没有冷却期），一段行情可能被重复计算。",
             "停牌的日子、" + ("" if keep_st else "ST 股票、") + f"上市不到 {MIN_LISTED_DAYS} 个交易日的股票不计入。",
             "这是历史统计，不代表以后，也不是对任何股票的买卖建议。"]
    if total < FEW_EVENTS:
        notes.insert(0, f"只有 {total} 次，样本太少，结果很不稳定，不要据此下结论。")
    return {
        "conditions": [c["label"] for c in conditions], "scope": SCOPES[scope], "industries": industries,
        "start": start.isoformat(), "end": end.isoformat(), "cooldown": cooldown, "keep_st": keep_st,
        "events": total, "stocks": int(len(set(cols.tolist()))) if total else 0,
        "eligible_days": int(base_np.sum()),
        "horizons": {str(h): value for h, value in horizons.items()}, "main_horizon": MAIN_HORIZON,
        "histogram": {"labels": BIN_LABELS, "events": _histogram(main_change[events]), "all": _histogram(main_change[base_np])},
        "path": _path(close, base_np, rows, cols, p.last_position.to_numpy(), horizons) if total else None,
        "by_year": by_year, "recent": recent, "coverage": coverage, "notes": notes,
    }
