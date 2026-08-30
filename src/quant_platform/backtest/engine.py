"""Point-in-time daily backtest engine."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from uuid import uuid4

import pandas as pd

from quant_platform.accounts.account import Account
from quant_platform.backtest.analytics import analyze_backtest
from quant_platform.backtest.result import BacktestResult
from quant_platform.backtest.validity import assess_backtest_validity
from quant_platform.core.exceptions import BacktestValidityError
from quant_platform.data.interfaces import MarketDataRepository
from quant_platform.execution.models import Fill, Order
from quant_platform.execution.next_open import NextOpenExecutionModel
from quant_platform.execution.order_generator import OrderGenerator
from quant_platform.portfolio.equal_weight import EqualWeightPortfolio
from quant_platform.portfolio.models import TargetPosition
from quant_platform.risk.basic_rules import (
    PortfolioRiskAction,
    RiskDecision,
    evaluate_daily_portfolio_risk,
    evaluate_target_risk,
)
from quant_platform.risk.config import RiskLimits
from quant_platform.signals.models import Signal
from quant_platform.strategies.base import Strategy
from quant_platform.strategies.context import StrategyContext
from quant_platform.universe.base import Universe

RISK_EVENT_COLUMNS = [
    "trade_date",
    "strategy_id",
    "event_type",
    "decision",
    "action",
    "reason",
    "target_count",
    "total_weight",
    "max_weight",
    "current_total_weight",
    "current_max_weight",
    "current_drawdown",
]


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
        risk_free_rate: float = 0.0,
        risk_limits: RiskLimits | None = None,
        evaluation_mode: str = "in_sample",
        fixed_universe: bool = True,
    ) -> None:
        self.repository = repository
        self.universe = universe
        self.strategy = strategy
        self.portfolio = portfolio
        self.order_generator = order_generator
        self.execution_model = execution_model
        self.rebalance = rebalance
        self.risk_free_rate = risk_free_rate
        self.risk_limits = risk_limits or RiskLimits()
        self.evaluation_mode = evaluation_mode
        self.fixed_universe = fixed_universe

    def run(
        self,
        start_date: date,
        end_date: date,
        initial_cash: float,
        *,
        run_id: str | None = None,
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
        bars = bars.sort_values("trade_date").reset_index(drop=True)
        missing_fields = sorted(self.strategy.required_fields.difference(bars.columns))
        if missing_fields:
            raise ValueError(f"Market data does not satisfy strategy fields: {missing_fields}")
        rebalance_dates = self._rebalance_dates(dates)
        bars_by_date: dict[date, pd.DataFrame] = {
            timestamp.date(): group for timestamp, group in bars.groupby("trade_date", sort=False)
        }
        empty_day = bars.iloc[0:0].copy()

        account = Account(account_id=self.strategy.strategy_id, initial_cash=initial_cash)
        # 用回测起点之前的最后收盘价做估值底仓：区间内停牌、退市或数据缺失的
        # 股票不会被错误地按 0 估值，也不会在持仓记录里留下 None 价格。
        last_closing_prices: dict[str, float] = self._seed_closing_prices(
            bars, start_date
        )

        pending: dict[date, list[Order]] = {}
        all_signals: list[Signal] = []
        all_targets: list[TargetPosition] = []
        all_orders: list[Order] = []
        all_fills: list[Fill] = []
        nav_rows: list[dict[str, object]] = []
        position_rows: list[dict[str, object]] = []
        risk_rows: list[dict[str, object]] = []

        for index, trade_date in enumerate(dates):
            account.start_day()
            day_rows = bars_by_date.get(trade_date, empty_day)
            executed_orders, fills = self.execution_model.execute(
                pending.pop(trade_date, []), day_rows, account
            )
            all_orders.extend(executed_orders)
            all_fills.extend(fills)

            closing_prices: dict[str, float] = {}
            if not day_rows.empty:
                valid = day_rows[["symbol", "raw_close"]].dropna(subset=["raw_close"])
                closing_prices = {
                    str(symbol): float(price)
                    for symbol, price in zip(valid["symbol"], valid["raw_close"], strict=True)
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

            weights = self._position_weights(account, last_closing_prices, snapshot.equity)
            daily_risk = evaluate_daily_portfolio_risk(
                weights,
                self.risk_limits,
                strategy_id=self.strategy.strategy_id,
                trade_date=trade_date,
                current_drawdown=snapshot.drawdown,
            )
            risk_rows.append(
                {
                    "trade_date": trade_date,
                    "strategy_id": self.strategy.strategy_id,
                    "event_type": "DAILY_POSITION",
                    "decision": daily_risk.decision.value,
                    "action": daily_risk.action.value,
                    "reason": "；".join(daily_risk.reasons),
                    "target_count": len(daily_risk.targets),
                    "total_weight": sum(target.target_weight for target in daily_risk.targets),
                    "max_weight": max(
                        (target.target_weight for target in daily_risk.targets),
                        default=0.0,
                    ),
                    "current_total_weight": daily_risk.current_total_weight,
                    "current_max_weight": daily_risk.current_max_weight,
                    "current_drawdown": daily_risk.current_drawdown,
                }
            )
            if index + 1 < len(dates) and daily_risk.decision == RiskDecision.ADJUST:
                next_date = dates[index + 1]
                corrective_targets = list(daily_risk.targets)
                all_targets.extend(corrective_targets)
                corrective_orders = self.order_generator.generate(
                    targets=corrective_targets,
                    account=account,
                    signal_date=trade_date,
                    execution_date=next_date,
                    closing_prices=last_closing_prices,
                )
                pending[next_date] = corrective_orders
                continue
            if daily_risk.action == PortfolioRiskAction.STOP_NEW:
                continue

            if trade_date not in rebalance_dates or index + 1 >= len(dates):
                continue
            history = self._history_through(bars, trade_date)
            symbols = self.universe.select(trade_date, history)
            context = StrategyContext.create(
                trade_date,
                history,
                symbols,
                portfolio_drawdown=snapshot.drawdown,
            )
            context.require_fields(self.strategy.required_fields)
            signals = self.strategy.generate_signals(context)
            targets = self.portfolio.construct(signals)
            all_signals.extend(signals)
            all_targets.extend(targets)
            evaluation = evaluate_target_risk(
                targets,
                self.risk_limits,
                current_drawdown=snapshot.drawdown,
            )
            risk_rows.append(
                {
                    "trade_date": trade_date,
                    "strategy_id": self.strategy.strategy_id,
                    "event_type": "TARGET_PORTFOLIO",
                    "decision": evaluation.decision.value,
                    "action": PortfolioRiskAction.NONE.value,
                    "reason": "；".join(evaluation.reasons),
                    "target_count": evaluation.target_count,
                    "total_weight": evaluation.total_weight,
                    "max_weight": evaluation.max_weight,
                    "current_total_weight": daily_risk.current_total_weight,
                    "current_max_weight": daily_risk.current_max_weight,
                    "current_drawdown": evaluation.current_drawdown,
                }
            )
            if evaluation.decision != RiskDecision.PASS:
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

        nav = pd.DataFrame(nav_rows)
        signals_frame = pd.DataFrame([signal.to_dict() for signal in all_signals])
        targets_frame = pd.DataFrame([asdict(target) for target in all_targets])
        orders_frame = pd.DataFrame([asdict(order) for order in all_orders])
        fills_frame = pd.DataFrame([asdict(fill) for fill in all_fills])
        positions_frame = pd.DataFrame(position_rows)
        risk_frame = pd.DataFrame(risk_rows, columns=RISK_EVENT_COLUMNS)
        requested_bars = bars[
            bars["trade_date"].between(pd.Timestamp(start_date), pd.Timestamp(end_date))
        ]
        unknown_market = requested_bars[
            requested_bars.get(
                "quality_status",
                pd.Series("UNKNOWN_STATUS", index=requested_bars.index, dtype="string"),
            )
            .astype("string")
            .fillna("UNKNOWN_STATUS")
            .ne("OK")
        ]
        validity = assess_backtest_validity(
            nav,
            start_date=start_date,
            end_date=end_date,
            calendar=calendar,
            orders=orders_frame,
            unknown_market_rows=len(unknown_market),
            unknown_market_symbols=(
                int(unknown_market["symbol"].nunique()) if "symbol" in unknown_market.columns else 0
            ),
            evaluation_mode=self.evaluation_mode,
            fixed_universe=self.fixed_universe,
        )
        if validity.blocks_completion:
            errors = "；".join(
                issue.message for issue in validity.issues if issue.severity.value == "ERROR"
            )
            raise BacktestValidityError(errors or "回测有效性检查未通过")

        analytics = analyze_backtest(
            nav,
            orders_frame,
            fills_frame,
            positions_frame,
            initial_cash=initial_cash,
            risk_free_rate=self.risk_free_rate,
        )
        analytics.summary.update(
            {
                "risk_checks": len(risk_frame),
                "risk_rejections": (
                    int(risk_frame["decision"].eq(RiskDecision.REJECT.value).sum())
                    if not risk_frame.empty
                    else 0
                ),
                "risk_adjustments": (
                    int(risk_frame["decision"].eq(RiskDecision.ADJUST.value).sum())
                    if not risk_frame.empty
                    else 0
                ),
                "validity_status": validity.status.value,
                "metrics_reliable": validity.metrics_reliable,
                "evaluation_mode": self.evaluation_mode,
                "validity_audit_version": validity.audit_version,
                "unknown_market_rows": validity.unknown_market_rows,
                "unknown_market_symbols": validity.unknown_market_symbols,
                "unknown_status_orders": validity.unknown_status_orders,
            }
        )
        return BacktestResult(
            run_id=run_id or str(uuid4()),
            nav=nav,
            signals=signals_frame,
            targets=targets_frame,
            orders=orders_frame,
            fills=fills_frame,
            trades=analytics.trades,
            positions=positions_frame,
            risk_events=risk_frame,
            summary=analytics.summary,
            validity=validity.to_dict(),
        )

    @staticmethod
    def _position_weights(
        account: Account, closing_prices: dict[str, float], equity: float
    ) -> dict[str, float]:
        if equity <= 0:
            return {}
        return {
            symbol: position.quantity * closing_prices.get(symbol, 0.0) / equity
            for symbol, position in account.positions.items()
            if position.quantity > 0 and closing_prices.get(symbol, 0.0) > 0
        }

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

    @staticmethod
    def _seed_closing_prices(bars: pd.DataFrame, start_date: date) -> dict[str, float]:
        """Return each symbol's latest close strictly before ``start_date``."""

        if bars.empty or "raw_close" not in bars.columns:
            return {}
        prior = bars[
            (bars["trade_date"] < pd.Timestamp(start_date)) & bars["raw_close"].notna()
        ]
        if prior.empty:
            return {}
        latest = prior.groupby("symbol", observed=True).tail(1)
        return {
            str(symbol): float(price)
            for symbol, price in zip(latest["symbol"], latest["raw_close"], strict=True)
            if float(price) > 0
        }

    @staticmethod
    def _history_through(bars: pd.DataFrame, trade_date: date) -> pd.DataFrame:
        """Return all bars up to ``trade_date`` using an already-sorted frame."""

        position = bars["trade_date"].searchsorted(pd.Timestamp(trade_date), side="right")
        return bars.iloc[: int(position)]
