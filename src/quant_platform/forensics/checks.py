"""Conservative checks: execution-model rejections are not proof of impossibility."""

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

VERSION = "external-trades-v1"
ORDER = ["发现明确矛盾", "存在疑点", "证据不足", "未发现异常"]


def load_evidence(root: Path, trades: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read only the requested symbols/dates; never create or update the repository."""
    symbols = trades.symbol.unique().tolist()
    start, end = trades.date.min(), trades.date.max()
    master_path = root / "security_master.parquet"
    master = pd.read_parquet(master_path) if master_path.exists() else pd.DataFrame()
    partitioned = root / "daily_bars"
    files = sorted(partitioned.rglob("*.parquet")) if partitioned.exists() else []
    if not files and (root / "daily_bars.parquet").exists():
        files = [root / "daily_bars.parquet"]
    frames = []
    for file in files:
        frames.append(
            pq.read_table(
                file,
                filters=[
                    ("symbol", "in", symbols),
                    ("trade_date", ">=", start.to_pydatetime()),
                    ("trade_date", "<=", end.to_pydatetime()),
                ],
            ).to_pandas()
        )
    frames = [frame for frame in frames if not frame.empty]
    return master, pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def check_trades(
    trades: pd.DataFrame, master: pd.DataFrame, bars: pd.DataFrame, raw_prices: bool = True
) -> pd.DataFrame:
    findings = []
    master_groups = dict(tuple(master.groupby("symbol"))) if not master.empty else {}
    if not bars.empty:
        bars = bars.copy()
        bars["trade_date"] = pd.to_datetime(bars.trade_date).dt.normalize()
    bar_groups = dict(tuple(bars.groupby(["symbol", "trade_date"]))) if not bars.empty else {}
    totals = trades.groupby(["symbol", "date", "side"]).quantity.sum()
    for trade in trades.itertuples(index=False):

        def add(check, status, claim, reference, source, trade=trade):
            findings.append(
                {
                    "表格行": trade.row,
                    "日期": str(trade.date.date()),
                    "股票": trade.symbol,
                    "核查项": check,
                    "结论": status,
                    "声称值": str(claim),
                    "证据或限制": str(reference),
                    "数据来源": str(source),
                    "规则版本": VERSION,
                }
            )

        security = master_groups.get(trade.symbol)
        if security is None or len(security) != 1:
            add(
                "时间线",
                ORDER[2],
                trade.side,
                "缺少唯一证券主数据，代码或证券类型待核实",
                "security_master",
            )
        else:
            row = security.iloc[0]
            listed = pd.to_datetime(row.get("list_date"), errors="coerce")
            delisted = pd.to_datetime(row.get("delist_date"), errors="coerce")
            if pd.isna(listed):
                add("时间线", ORDER[2], trade.side, "上市日期缺失", row.get("source", "主表"))
            elif trade.date < listed or (pd.notna(delisted) and trade.date >= delisted):
                add(
                    "时间线",
                    ORDER[0],
                    trade.side,
                    f"上市日期 {listed}；退市日期 {delisted}；仅核查上市股票竞价交易",
                    row.get("source", "主表"),
                )
            else:
                add(
                    "时间线",
                    ORDER[3],
                    trade.side,
                    f"上市 {listed.date()}；退市 {delisted}",
                    row.get("source", "主表"),
                )
        matches = bar_groups.get((trade.symbol, trade.date))
        if matches is None or len(matches) != 1:
            add(
                "行情覆盖",
                ORDER[2],
                trade.price,
                "当天行情缺失或存在重复，不能推断未成交",
                "daily_bars",
            )
            continue
        bar = matches.iloc[0]
        source = f"{bar.get('source', '未知')} / 入库 {bar.get('ingested_at', '未记录')}"
        if str(bar.get("quality_status")) != "OK":
            add(
                "行情质量",
                ORDER[2],
                trade.price,
                f"行情质量标记 {bar.get('quality_status', '缺失')}，跳过成交判断",
                source,
            )
            continue
        suspended = bar.get("is_suspended")
        if pd.isna(suspended):
            add("停牌状态", ORDER[2], trade.side, "停牌状态缺失", source)
        elif suspended:
            add(
                "停牌状态", ORDER[0], trade.side, "本地行情标记全天停牌；需核实原始成交类型", source
            )
        else:
            add("停牌状态", ORDER[3], trade.side, "本地行情未标记停牌", source)
        low, high = bar.get("raw_low"), bar.get("raw_high")
        if not raw_prices or pd.isna(low) or pd.isna(high) or low <= 0 or high < low:
            add("成交价格", ORDER[2], trade.price, "未确认未复权价或本地价格范围无效", source)
        else:
            outside = trade.price < low - 0.005 or trade.price > high + 0.005
            add(
                "成交价格",
                ORDER[0] if outside else ORDER[3],
                trade.price,
                f"当日未复权范围 [{low}, {high}]；容差0.005元",
                source,
            )
            limit = bar.get("up_limit" if trade.side == "BUY" else "down_limit")
            if pd.notna(limit) and abs(high - low) < 0.005 and abs(high - limit) < 0.005:
                add(
                    "一字板成交",
                    ORDER[1],
                    trade.side,
                    "当日价格处于一字涨/跌停；日线不能证明委托排队位置或成交概率",
                    source,
                )
        volume = bar.get("volume")
        quantity = totals.loc[(trade.symbol, trade.date, trade.side)]
        if pd.isna(volume) or volume < 0:
            add("成交占比", ORDER[2], quantity, "成交量缺失或无效，不能计算占比", source)
        else:
            status = (
                ORDER[0]
                if quantity > volume
                else (ORDER[1] if quantity > volume * 0.1 else ORDER[3])
            )
            add(
                "成交占比",
                status,
                f"同日同方向合计{quantity:g}股",
                f"本地当日成交量{volume:g}股；超过10%仅提示疑点；须确保记录不重复且成交量口径一致",
                source,
            )
    return pd.DataFrame(findings)


def verdict(findings: pd.DataFrame) -> str:
    return next((label for label in ORDER if label in set(findings["结论"])), ORDER[2])


def markdown_report(findings: pd.DataFrame) -> str:
    lines = [
        "# 外部成交材料检查",
        "",
        f"结论：{verdict(findings)}",
        "",
        "仅核查普通上市股票竞价成交。未发现异常不代表策略有效；缺失证据不构成违规。",
        "本报告不核查净值、换手率、完整账户或策略代码。",
        "",
    ]
    for row in findings.to_dict("records"):
        lines += [f"## 第{row['表格行']}行 · {row['股票']} · {row['日期']} · {row['核查项']}", ""]
        lines += [
            f"{key}：{str(row[key]).replace(chr(10), ' ')}  "
            for key in ("结论", "声称值", "证据或限制", "数据来源", "规则版本")
        ]
        lines.append("")
    return "\n".join(lines)
