"""One persisted backtest's trades per stock, shaped for drawing on a K-line."""
from __future__ import annotations

from math import isfinite
from pathlib import Path

import pandas as pd

from .symbols import to_bare, to_canonical

REJECT_LABELS = {
    "MISSING_EXECUTION_BAR": "成交日没有行情",
    "INVALID_EXECUTION_PRICE": "开盘价无效",
    "SUSPENDED": "停牌",
    "UNKNOWN_SUSPENSION_STATUS": "停牌状态未知",
    "UNKNOWN_MARKET_STATUS": "行情状态未知",
    "MARKET_DATA_NOT_TRADABLE": "行情数据不可交易",
    "UNKNOWN_PRICE_LIMIT": "涨跌停价未知",
    "OPEN_AT_UPPER_LIMIT": "开盘涨停，无法买入",
    "OPEN_AT_LOWER_LIMIT": "开盘跌停，无法卖出",
    "INSUFFICIENT_CASH_OR_QUANTITY": "资金或可卖数量不足",
    "LIQUIDITY_LIMIT": "超过成交量参与率上限",
    "MISSING_LIQUIDITY": "缺少成交量数据",
    "DAILY_ORDER_LIMIT": "超过当日订单数上限",
    "IMPACT_OUTSIDE_LIMIT": "冲击后价格超出涨跌停",
}
_UNFILLED = {"REJECTED", "FAILED"}


def _read(directory: Path, name: str, columns: list[str]) -> pd.DataFrame:
    try:
        frame = pd.read_parquet(directory / f"{name}.parquet")
    except (OSError, ValueError):
        return pd.DataFrame(columns=columns)
    return frame.reindex(columns=columns)


def _number(value: object, digits: int) -> float | None:
    number = pd.to_numeric(value, errors="coerce")
    return round(float(number), digits) if isfinite(number) else None


def _dates(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, errors="coerce").dt.strftime("%Y-%m-%d")


def traded_symbols(directory: Path, names: dict[str, str]) -> list[dict]:
    """Every stock the run filled or failed to fill, most traded first."""
    fills = _read(directory, "fills", ["symbol", "side"])
    orders = _read(directory, "orders", ["symbol", "status"])
    counts: dict[str, dict[str, int]] = {}
    for symbol, side in zip(fills["symbol"], fills["side"], strict=True):
        row = counts.setdefault(str(symbol), {"buys": 0, "sells": 0, "rejected": 0})
        row["buys" if str(side) == "BUY" else "sells"] += 1
    for symbol in orders.loc[orders["status"].isin(_UNFILLED), "symbol"]:
        counts.setdefault(str(symbol), {"buys": 0, "sells": 0, "rejected": 0})["rejected"] += 1
    rows = [{"symbol": to_bare(symbol), "name": names.get(to_canonical(symbol), "名称待补充"), **count}
            for symbol, count in counts.items()]
    return sorted(rows, key=lambda row: (-(row["buys"] + row["sells"]), -row["rejected"], row["symbol"]))


def symbol_trades(directory: Path, symbol: str) -> dict:
    """Fills at raw prices, unfilled orders with reasons, and end-of-day holding spans."""
    canonical = to_canonical(symbol)
    fills = _read(directory, "fills", ["symbol", "trade_date", "side", "quantity", "price", "reference_price",
                                       "commission", "stamp_tax", "transfer_fee", "slippage_cost"])
    fills = fills[fills["symbol"].astype(str).map(to_canonical) == canonical].copy()
    fills["date"] = _dates(fills["trade_date"])
    costs = ["commission", "stamp_tax", "transfer_fee", "slippage_cost"]
    fills[costs] = fills[costs].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    fills = fills.dropna(subset=["date"]).sort_values("date")

    orders = _read(directory, "orders", ["symbol", "execution_date", "side", "quantity", "status", "reject_reason"])
    orders = orders[(orders["symbol"].astype(str).map(to_canonical) == canonical) & orders["status"].isin(_UNFILLED)].copy()
    orders["date"] = _dates(orders["execution_date"])
    orders = orders.dropna(subset=["date"]).sort_values("date")

    positions = _read(directory, "positions", ["symbol", "trade_date", "quantity"])
    held = positions[(positions["symbol"].astype(str).map(to_canonical) == canonical)
                     & (pd.to_numeric(positions["quantity"], errors="coerce") > 0)]
    held_days = set(_dates(held["trade_date"]).dropna())
    # The run's own valuation days define adjacency: a holding span breaks on any day without a position.
    sessions = sorted(set(_dates(_read(directory, "nav", ["trade_date"])["trade_date"]).dropna()) | held_days)
    holdings: list[dict] = []
    current = None
    for day in sessions:
        if day not in held_days:
            current = None
        elif current is None:
            current = {"start_date": day, "end_date": day}
            holdings.append(current)
        else:
            current["end_date"] = day
    return {
        "symbol": to_bare(canonical),
        "fills": [{"date": row.date, "side": str(row.side), "quantity": int(row.quantity),
                   "price": _number(row.price, 4), "reference_price": _number(row.reference_price, 4),
                   "fees": _number(row.commission + row.stamp_tax + row.transfer_fee, 2),
                   "slippage_cost": _number(row.slippage_cost, 2)}
                  for row in fills.itertuples() if _number(row.price, 4)],
        "rejected": [{"date": row.date, "side": str(row.side), "quantity": int(row.quantity),
                      "reason": str(row.reject_reason or ""),
                      "reason_label": REJECT_LABELS.get(str(row.reject_reason or ""), "订单未成交")}
                     for row in orders.itertuples()],
        "holdings": holdings,
    }
