"""Trading, cost, and portfolio analytics for completed backtests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from quant_platform.backtest.metrics import TRADING_DAYS_PER_YEAR, calculate_metrics

TRADE_COLUMNS = [
    "symbol",
    "buy_order_id",
    "sell_order_id",
    "buy_date",
    "sell_date",
    "quantity",
    "buy_price",
    "sell_price",
    "buy_reference_price",
    "sell_reference_price",
    "gross_pnl",
    "direct_cost",
    "slippage_cost",
    "net_pnl",
    "return_rate",
    "holding_days",
]


@dataclass
class _OpenLot:
    order_id: str
    trade_date: pd.Timestamp
    quantity: int
    price: float
    reference_price: float
    direct_cost_per_share: float
    slippage_per_share: float


@dataclass(frozen=True)
class BacktestAnalytics:
    """Calculated summary and reconstructed closed trades."""

    summary: dict[str, Any]
    trades: pd.DataFrame


def analyze_backtest(
    nav: pd.DataFrame,
    orders: pd.DataFrame,
    fills: pd.DataFrame,
    positions: pd.DataFrame,
    *,
    initial_cash: float,
    risk_free_rate: float = 0.0,
) -> BacktestAnalytics:
    """Build the complete backward-compatible summary for one run."""

    summary = calculate_metrics(
        nav, initial_cash=initial_cash, risk_free_rate=risk_free_rate
    )
    trades = build_closed_trades(fills)
    summary.update(_execution_metrics(nav, orders, fills, trades, initial_cash))
    summary.update(_portfolio_metrics(nav, positions))
    summary.update(
        {
            "initial_cash": initial_cash,
            "final_equity": (
                float(pd.to_numeric(nav["equity"], errors="coerce").iloc[-1])
                if not nav.empty
                else initial_cash
            ),
        }
    )
    return BacktestAnalytics(summary=summary, trades=trades)


def build_closed_trades(fills: pd.DataFrame) -> pd.DataFrame:
    """Reconstruct FIFO round trips and allocate all costs to closed lots."""

    if fills.empty:
        return pd.DataFrame(columns=TRADE_COLUMNS)
    required = {"order_id", "symbol", "side", "quantity", "price", "trade_date"}
    missing = sorted(required.difference(fills.columns))
    if missing:
        raise ValueError(f"fills are missing columns: {missing}")

    working = fills.copy()
    working["trade_date"] = pd.to_datetime(working["trade_date"], errors="coerce")
    working["_sequence"] = range(len(working))
    sort_columns = ["trade_date"]
    if "filled_at" in working:
        sort_columns.append("filled_at")
    sort_columns.append("_sequence")
    working = working.sort_values(sort_columns)

    lots: dict[str, list[_OpenLot]] = {}
    closed: list[dict[str, Any]] = []
    for row in working.to_dict(orient="records"):
        symbol = str(row["symbol"])
        side = str(row["side"])
        quantity = int(row["quantity"])
        price = float(row["price"])
        reference_price = _optional_float(row.get("reference_price"), price)
        commission = _optional_float(row.get("commission"), 0.0)
        stamp_tax = _optional_float(row.get("stamp_tax"), 0.0)
        slippage = _optional_float(row.get("slippage_cost"), 0.0)
        trade_date = pd.Timestamp(row["trade_date"])
        if quantity <= 0:
            raise ValueError("fill quantity must be positive")

        if side == "BUY":
            lots.setdefault(symbol, []).append(
                _OpenLot(
                    order_id=str(row["order_id"]),
                    trade_date=trade_date,
                    quantity=quantity,
                    price=price,
                    reference_price=reference_price,
                    direct_cost_per_share=(commission + stamp_tax) / quantity,
                    slippage_per_share=slippage / quantity,
                )
            )
            continue
        if side != "SELL":
            raise ValueError(f"unsupported fill side: {side}")

        remaining = quantity
        sell_cost_per_share = (commission + stamp_tax) / quantity
        sell_slippage_per_share = slippage / quantity
        symbol_lots = lots.setdefault(symbol, [])
        while remaining > 0:
            if not symbol_lots:
                raise ValueError(f"sell fill exceeds open quantity for {symbol}")
            lot = symbol_lots[0]
            matched = min(remaining, lot.quantity)
            direct_cost = matched * (
                lot.direct_cost_per_share + sell_cost_per_share
            )
            slippage_cost = matched * (
                lot.slippage_per_share + sell_slippage_per_share
            )
            gross_pnl = matched * (reference_price - lot.reference_price)
            net_pnl = gross_pnl - direct_cost - slippage_cost
            capital = matched * lot.reference_price + matched * (
                lot.direct_cost_per_share + lot.slippage_per_share
            )
            closed.append(
                {
                    "symbol": symbol,
                    "buy_order_id": lot.order_id,
                    "sell_order_id": str(row["order_id"]),
                    "buy_date": lot.trade_date.date(),
                    "sell_date": trade_date.date(),
                    "quantity": matched,
                    "buy_price": lot.price,
                    "sell_price": price,
                    "buy_reference_price": lot.reference_price,
                    "sell_reference_price": reference_price,
                    "gross_pnl": gross_pnl,
                    "direct_cost": direct_cost,
                    "slippage_cost": slippage_cost,
                    "net_pnl": net_pnl,
                    "return_rate": net_pnl / capital if capital > 0 else 0.0,
                    "holding_days": max((trade_date - lot.trade_date).days, 0),
                }
            )
            lot.quantity -= matched
            remaining -= matched
            if lot.quantity == 0:
                symbol_lots.pop(0)

    return pd.DataFrame(closed, columns=TRADE_COLUMNS)


def _execution_metrics(
    nav: pd.DataFrame,
    orders: pd.DataFrame,
    fills: pd.DataFrame,
    trades: pd.DataFrame,
    initial_cash: float,
) -> dict[str, Any]:
    order_count = len(orders)
    fill_count = len(fills)
    statuses = (
        orders["status"].astype(str) if "status" in orders else pd.Series(dtype=str)
    )
    sides = fills["side"].astype(str) if "side" in fills else pd.Series(dtype=str)
    filled_order_count = (
        int(fills["order_id"].nunique()) if "order_id" in fills else 0
    )

    commission = _column_sum(fills, "commission")
    stamp_tax = _column_sum(fills, "stamp_tax")
    slippage_cost = _column_sum(fills, "slippage_cost")
    total_cost = commission + stamp_tax + slippage_cost
    traded_notional = (
        float(
            (
                pd.to_numeric(fills["quantity"], errors="coerce")
                * pd.to_numeric(fills["price"], errors="coerce")
            ).sum()
        )
        if {"quantity", "price"}.issubset(fills.columns)
        else 0.0
    )
    equity = (
        pd.to_numeric(nav["equity"], errors="coerce").dropna()
        if "equity" in nav
        else pd.Series(dtype=float)
    )
    average_equity = float(equity.mean()) if not equity.empty else initial_cash
    period_turnover = (
        traded_notional / (2.0 * average_equity) if average_equity > 0 else 0.0
    )
    periods = max(len(equity) - 1, 1)

    winning = trades[trades["net_pnl"] > 0] if not trades.empty else trades
    losing = trades[trades["net_pnl"] < 0] if not trades.empty else trades
    gross_profit = float(winning["net_pnl"].sum()) if not winning.empty else 0.0
    gross_loss = float(losing["net_pnl"].sum()) if not losing.empty else 0.0
    average_win = float(winning["net_pnl"].mean()) if not winning.empty else None
    average_loss = float(losing["net_pnl"].mean()) if not losing.empty else None
    return {
        "orders": order_count,
        "fills": fill_count,
        "filled_orders": filled_order_count,
        "rejected_orders": int((statuses == "REJECTED").sum()),
        "failed_orders": int((statuses == "FAILED").sum()),
        "order_fill_rate": filled_order_count / order_count if order_count else 0.0,
        "buy_fills": int((sides == "BUY").sum()),
        "sell_fills": int((sides == "SELL").sum()),
        "closed_trades": len(trades),
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "trade_win_rate": len(winning) / len(trades) if len(trades) else 0.0,
        "average_trade_pnl": (
            float(trades["net_pnl"].mean()) if not trades.empty else None
        ),
        "average_win": average_win,
        "average_loss": average_loss,
        "payoff_ratio": (
            average_win / abs(average_loss)
            if average_win is not None and average_loss not in (None, 0.0)
            else None
        ),
        "profit_factor": (
            gross_profit / abs(gross_loss) if gross_loss < 0 else None
        ),
        "max_trade_profit": (
            float(trades["net_pnl"].max()) if not trades.empty else None
        ),
        "max_trade_loss": (
            float(trades["net_pnl"].min()) if not trades.empty else None
        ),
        "average_holding_days": (
            float(trades["holding_days"].mean()) if not trades.empty else None
        ),
        "max_holding_days": (
            int(trades["holding_days"].max()) if not trades.empty else None
        ),
        "realized_gross_pnl": (
            float(trades["gross_pnl"].sum()) if not trades.empty else 0.0
        ),
        "realized_net_pnl": (
            float(trades["net_pnl"].sum()) if not trades.empty else 0.0
        ),
        "commission": commission,
        "stamp_tax": stamp_tax,
        "slippage_cost": slippage_cost,
        "total_transaction_cost": total_cost,
        "transaction_cost_to_initial_cash": (
            total_cost / initial_cash if initial_cash > 0 else 0.0
        ),
        "traded_notional": traded_notional,
        "portfolio_turnover": period_turnover,
        "annualized_turnover": period_turnover * TRADING_DAYS_PER_YEAR / periods,
    }


def _portfolio_metrics(nav: pd.DataFrame, positions: pd.DataFrame) -> dict[str, Any]:
    if nav.empty or "trade_date" not in nav:
        return {}
    working_nav = nav.copy()
    working_nav["trade_date"] = pd.to_datetime(working_nav["trade_date"])
    equity = pd.to_numeric(working_nav["equity"], errors="coerce")
    market_value = pd.to_numeric(
        working_nav.get("market_value", pd.Series(0.0, index=working_nav.index)),
        errors="coerce",
    ).fillna(0.0)
    cash = pd.to_numeric(
        working_nav.get("cash", pd.Series(0.0, index=working_nav.index)),
        errors="coerce",
    ).fillna(0.0)
    safe_equity = equity.where(equity > 0)
    exposure = (market_value / safe_equity).fillna(0.0)
    cash_ratio = (cash / safe_equity).fillna(0.0)

    nav_dates = pd.Index(working_nav["trade_date"].dt.normalize().unique())
    position_counts = pd.Series(0, index=nav_dates, dtype=float)
    average_concentration = 0.0
    max_concentration = 0.0
    max_single_weight = 0.0
    if not positions.empty and {"trade_date", "market_value"}.issubset(
        positions.columns
    ):
        working_positions = positions.copy()
        working_positions["trade_date"] = pd.to_datetime(
            working_positions["trade_date"]
        ).dt.normalize()
        position_counts = (
            working_positions.groupby("trade_date", observed=True)["symbol"]
            .nunique()
            .reindex(nav_dates, fill_value=0)
            .astype(float)
        )
        dated_equity = working_nav.set_index(
            working_nav["trade_date"].dt.normalize()
        )["equity"]
        working_positions["weight"] = pd.to_numeric(
            working_positions["market_value"], errors="coerce"
        ) / working_positions["trade_date"].map(dated_equity)
        concentration = working_positions.groupby("trade_date", observed=True)[
            "weight"
        ].apply(lambda values: float((values.fillna(0.0) ** 2).sum()))
        concentration = concentration.reindex(nav_dates, fill_value=0.0)
        average_concentration = float(concentration.mean())
        max_concentration = float(concentration.max())
        max_single_weight = float(working_positions["weight"].fillna(0.0).max())

    return {
        "average_position_count": float(position_counts.mean()),
        "max_position_count": int(position_counts.max()),
        "average_exposure": float(exposure.mean()),
        "max_exposure": float(exposure.max()),
        "average_cash_ratio": float(cash_ratio.mean()),
        "minimum_cash_ratio": float(cash_ratio.min()),
        "time_in_market_ratio": float((exposure > 1e-12).mean()),
        "max_single_position_weight": max_single_weight,
        "average_concentration_hhi": average_concentration,
        "max_concentration_hhi": max_concentration,
    }


def _column_sum(frame: pd.DataFrame, column: str) -> float:
    if column not in frame:
        return 0.0
    return float(pd.to_numeric(frame[column], errors="coerce").fillna(0.0).sum())


def _optional_float(value: Any, default: float) -> float:
    if value is None or pd.isna(value):
        return default
    return float(value)
