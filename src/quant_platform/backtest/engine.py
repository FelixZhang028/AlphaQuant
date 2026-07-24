"""Point-in-time daily backtest engine."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from uuid import uuid4

import pandas as pd

from quant_platform.accounts.account import Account
from quant_platform.backtest.metrics import calculate_metrics
from quant_platform.backtest.result import BacktestResult
from quant_platform.data.interfaces import MarketDataRepository
from quant_platform.execution.models import Fill, Order
from quant_platform.execution.next_open import NextOpenExecutionModel
from quant_platform.execution.order_generator import OrderGenerator
from quant_platform.portfolio.equal_weight import EqualWeightPortfolio
from quant_platform.portfolio.models import TargetPosition
from quant_platform.risk.basic_rules import RiskDecision, validate_target_weights
from quant_platform.signals.models import Signal
from quant_platform.strategies.base import Strategy
from quant_platform.strategies.context import StrategyContext
from quant_platform.universe.base import Universe


class BacktestEngine:
    """Run signals at close and execute their orders at the next trading-day open."""

    def __init__(
        self,
        repository: MarketDataRepository,
        universe: Universe,
        strategy: Strategy,
        portfolio: EqualWeightPortfolio,
        order_generator: OrderGenerator,
        execution_model: NextOpenExecutionModel,
        rebalance: str = "weekly",
    ) -> None:
        self.repository = repository
        self.universe = universe
        self.strategy = strategy
        self.portfolio = portfolio
        self.order_generator = order_generator
        self.execution_model = execution_model
        self.rebalance = rebalance

    def run(
        self, start_date: date, end_date: date, initial_cash: float
    ) -> BacktestResult:
        """Execute a deterministic long-only backtest over the requested dates."""

        calendar = self.repository.get_trade_calendar(start_date, end_date)
        if calendar.empty:
            raise ValueError("No trading calendar data in requested range")
        dates = [timestamp.date() for timestamp in pd.to_datetime(calendar["cal_date"])]
        bars = self.repository.get_daily_bars(end_date=end_date)
        if bars.empty:
            raise ValueError("No daily bars available for backtest")
        bars["trade_date"] = pd.to_datetime(bars["trade_date"]).dt.normalize()
        missing_fields = sorted(self.strategy.required_fields.difference(bars.columns))
        if missing_fields:
            raise ValueError(
                f"Market data does not satisfy strategy fields: {missing_fields}"
            )
        rebalance_dates = self._rebalance_dates(dates)

        account = Account(
            account_id=self.strategy.strategy_id, initial_cash=initial_cash
        )
        last_closing_prices: dict[str, float] = {}

        pending: dict[date, list[Order]] = {}
        all_signals: list[Signal] = []
        all_targets: list[TargetPosition] = []
        all_orders: list[Order] = []
        all_fills: list[Fill] = []
        nav_rows: list[dict[str, object]] = []
        position_rows: list[dict[str, object]] = []

        for index, trade_date in enumerate(dates):
            account.start_day()
            day_rows = bars[bars["trade_date"] == pd.Timestamp(trade_date)]
            executed_orders, fills = self.execution_model.execute(
                pending.pop(trade_date, []), day_rows, account
            )
            all_orders.extend(executed_orders)
            all_fills.extend(fills)

            closing_prices = {
                str(row["symbol"]): float(row["raw_close"])
                for _, row in day_rows.iterrows()
                if pd.notna(row["raw_close"])
            }
            last_closing_prices.update(closing_prices)
            snapshot = account.mark_to_market(trade_date, last_closing_prices)
            nav_rows.append(asdict(snapshot))
            for symbol, position in sorted(account.positions.items()):
                valuation_price = last_closing_prices.get(symbol)
                position_rows.append(
                    {
                        "trade_date": trade_date,
                        "symbol": symbol,
                        "quantity": position.quantity,
                        "available_quantity": position.available_quantity,
                        "average_cost": position.average_cost,
                        "close": valuation_price,
                        "market_value": position.quantity
                        * (valuation_price if valuation_price is not None else 0.0),
                    }
                )

            if trade_date not in rebalance_dates or index + 1 >= len(dates):
                continue
            history = bars[bars["trade_date"] <= pd.Timestamp(trade_date)]
            symbols = self.universe.select(trade_date, history)
            context = StrategyContext.create(trade_date, history, symbols)
            context.require_fields(self.strategy.required_fields)
            signals = self.strategy.generate_signals(context)
            targets = self.portfolio.construct(signals)
            if validate_target_weights(targets) != RiskDecision.PASS:
                continue
            next_date = dates[index + 1]
            orders = self.order_generator.generate(
                targets=targets,
                account=account,
                signal_date=trade_date,
                execution_date=next_date,
                closing_prices=last_closing_prices,
            )
            pending.setdefault(next_date, []).extend(orders)
            all_signals.extend(signals)
            all_targets.extend(targets)

        nav = pd.DataFrame(nav_rows)
        summary = calculate_metrics(nav)
        summary.update(
            {
                "initial_cash": initial_cash,
                "final_equity": float(nav.iloc[-1]["equity"]),
                "orders": len(all_orders),
                "fills": len(all_fills),
                "rejected_orders": sum(
                    order.status == "REJECTED" for order in all_orders
                ),
                "commission": sum(fill.commission for fill in all_fills),
                "stamp_tax": sum(fill.stamp_tax for fill in all_fills),
            }
        )
        return BacktestResult(
            run_id=str(uuid4()),
            nav=nav,
            signals=pd.DataFrame([signal.to_dict() for signal in all_signals]),
            targets=pd.DataFrame([asdict(target) for target in all_targets]),
            orders=pd.DataFrame([asdict(order) for order in all_orders]),
            fills=pd.DataFrame([asdict(fill) for fill in all_fills]),
            positions=pd.DataFrame(position_rows),
            summary=summary,
        )

    def _rebalance_dates(self, dates: list[date]) -> set[date]:
        frame = pd.DataFrame({"trade_date": pd.to_datetime(dates)})
        if self.rebalance == "daily":
            return set(dates)
        if self.rebalance == "monthly":
            periods = frame["trade_date"].dt.to_period("M")
        elif self.rebalance == "weekly":
            periods = frame["trade_date"].dt.to_period("W-FRI")
        else:
            raise ValueError(f"Unsupported rebalance frequency: {self.rebalance}")
        frame["period"] = periods
        tails = frame.groupby("period", observed=True).tail(1)
        return {timestamp.date() for timestamp in tails["trade_date"]}
