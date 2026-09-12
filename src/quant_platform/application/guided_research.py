"""Guided idea templates and request-specific, read-only data checks."""

import json
from dataclasses import replace

import pandas as pd

from quant_platform.factors.registry import default_registry

IDEAS = {
    "趋势上涨": ("momentum_20", "优先选择过去20个交易日涨幅较高的股票。"),
    "短期超跌": ("reversal_5", "优先选择过去5个交易日跌幅较大的股票，检验短期反弹假设。"),
    "低波动": ("volatility_20", "优先选择过去20个交易日收益波动较小的股票。"),
}


def idea_request(service, idea, start, end, cash, top_n, rebalance):
    factor, _ = IDEAS[idea]
    return replace(
        service.default_request(),
        strategy_plugin="factor_composite",
        strategy_id="guided_" + factor,
        strategy_parameters={
            "factors_json": json.dumps(
                [{"name": factor, "weight": 1.0, "clip": True, "missing": "drop"}]
            )
        },
        start_date=start,
        end_date=end,
        initial_cash=float(cash),
        top_n=int(top_n),
        rebalance=rebalance,
        portfolio_method="equal_weight",
        universe_mode="fixed",
    )


def inspect_request(service, request):
    """Check actual request inputs; execution-time validity remains authoritative."""
    rows = []

    def add(item, ok, detail):
        rows.append({"检查项目": item, "状态": "通过" if ok else "需处理", "说明": detail})

    if request.start_date > request.end_date:
        add("日期", False, "开始日期不能晚于结束日期。")
        return pd.DataFrame(rows)
    engine, _ = service.build_engine(request)
    repo = engine.repository
    symbols = list(engine.universe.symbols)
    if hasattr(engine.universe, "period_symbols"):
        symbols = list(engine.universe.period_symbols(request.start_date, request.end_date))
    add("股票池", bool(symbols), f"本次研究包含 {len(symbols)} 只股票。")
    calendar = repo.get_trade_calendar(request.start_date, request.end_date)
    add("交易日历", not calendar.empty, "需要覆盖研究区间的交易日历。")
    if calendar.empty or not symbols:
        return pd.DataFrame(rows)
    dates = pd.to_datetime(calendar.cal_date).dt.normalize()
    full_calendar = repo.read_table("trade_calendar")
    known_dates = pd.to_datetime(full_calendar.cal_date)
    add(
        "日历覆盖范围",
        known_dates.min() <= pd.Timestamp(request.start_date)
        and known_dates.max() >= pd.Timestamp(request.end_date),
        f"本地日历范围 {known_dates.min().date()} 至 {known_dates.max().date()}；"
        "研究起止日期必须在已覆盖范围内。",
    )
    start = engine._warmup_start_date(request.start_date)
    bars = repo.get_daily_bars(symbols, start, request.end_date)
    required = {
        "symbol",
        "trade_date",
        "raw_open",
        "raw_close",
        "volume",
        "amount",
        "is_st",
        "is_listed",
        "is_suspended",
        "quality_status",
        "up_limit",
        "down_limit",
    }
    history = max(
        engine.universe.config.minimum_history_days,
        engine.universe.config.minimum_listing_days,
        2,
    )
    required.update(engine.strategy.required_fields)
    if request.strategy_plugin == "factor_composite":
        registry = default_registry()
        for spec in json.loads(request.strategy_parameters["factors_json"]):
            factor = registry.get(spec["name"])
            required.update(factor.required_fields)
            history = max(history, factor.min_history)
    missing = sorted(required - set(bars.columns))
    add("行情字段", not missing, "字段齐全。" if not missing else "缺少字段：" + "、".join(missing))
    if missing:
        return pd.DataFrame(rows)
    bars = bars.copy()
    bars["trade_date"] = pd.to_datetime(bars.trade_date).dt.normalize()
    early = bars[bars.trade_date <= dates.min()].groupby("symbol").trade_date.nunique()
    short = [s for s in symbols if early.get(s, 0) < history]
    add(
        "回看历史", not short, f"起点需要至少 {history} 条历史；不足：" + ("、".join(short) or "无")
    )
    active = bars[bars.trade_date.isin(dates)]
    expected = pd.MultiIndex.from_product([symbols, dates.unique()], names=["symbol", "trade_date"])
    actual = pd.MultiIndex.from_frame(active[["symbol", "trade_date"]])
    absent = expected.difference(actual)
    add("区间行情", len(absent) == 0, f"按本地交易日历检查，缺少 {len(absent)} 条股票日线。")
    invalid = active[list(required)].isna().any(axis=1) | active.quality_status.ne("OK")
    add("行情状态", not invalid.any(), f"存在 {int(invalid.sum())} 条字段缺失或质量异常记录。")
    if engine.benchmark_symbol:
        benchmark = repo.read_table("benchmark_bars")
        covered = set()
        if {"symbol", "trade_date", "raw_close"}.issubset(benchmark.columns):
            chosen = benchmark[benchmark.symbol.eq(engine.benchmark_symbol)]
            chosen = chosen[pd.to_numeric(chosen.raw_close, errors="coerce").gt(0)]
            covered = set(pd.to_datetime(chosen.trade_date).dt.normalize())
        missing_days = set(dates) - covered
        add(
            "比较基准",
            not missing_days,
            f"{engine.benchmark_symbol} 缺少 {len(missing_days)} 个交易日的有效收盘价。",
        )
    return pd.DataFrame(rows)
