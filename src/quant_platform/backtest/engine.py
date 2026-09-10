"""Point-in-time daily backtest engine."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
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
        benchmark_symbol: str | None = None,
        warmup_days: int = 120,
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
        self.benchmark_symbol = benchmark_symbol
        self.warmup_days = warmup_days

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
        # 只加载股票池 × 回测区间 + warmup 缓冲的行情：策略动量与估值底仓
        # 都需要 start 之前的历史，但不需要全市场全历史。
        universe_symbols = self.universe.symbols
        load_start = self._warmup_start_date(start_date)
        bars = self.repository.get_daily_bars(
            symbols=list(universe_symbols) if universe_symbols else None,
            start_date=load_start,
            end_date=end_date,
        )
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
        # 复权因子底仓：同样取回测起点之前的最后有效因子，日内前向填充。
        last_adj_factors: dict[str, float] = self._seed_adj_factors(bars, start_date)
        # 基准净值列：首条基准行情锚定为 initial_cash，缺失日期前向填充。
        benchmark_equity = self._benchmark_equity_series(dates, initial_cash)

        pending: dict[date, list[Order]] = {}
        all_signals: list[Signal] = []
        all_targets: list[TargetPosition] = []
        all_orders: list[Order] = []
        all_fills: list[Fill] = []
        nav_rows: list[dict[str, object]] = []
        position_rows: list[dict[str, object]] = []
        risk_rows: list[dict[str, object]] = []

        missing_adj_factor_events = 0
        for index, trade_date in enumerate(dates):
            account.start_day()
            day_rows = bars_by_date.get(trade_date, empty_day)
            executed_orders, fills = self.execution_model.execute(
                pending.pop(trade_date, []), day_rows, account, adj_factors=last_adj_factors
            )
            all_orders.extend(executed_orders)
            all_fills.extend(fills)
            day_factors = self._valid_factors(day_rows)
            # 成交当日既无行因子也无历史因子 → 执行模型已回退比率 1，计入告警。
            missing_adj_factor_events += sum(
                1
                for fill in fills
                if fill.symbol not in day_factors and fill.symbol not in last_adj_factors
            )

            closing_prices: dict[str, float] = {}
            if not day_rows.empty:
                valid = day_rows[["symbol", "raw_close"]].dropna(subset=["raw_close"])
                closing_prices = {
                    str(symbol): float(price)
                    for symbol, price in zip(valid["symbol"], valid["raw_close"], strict=True)
                }
            last_closing_prices.update(closing_prices)
            last_adj_factors.update(day_factors)
            # 成本锚定估值价：raw_close × F(t)/cost_adj_factor；
            # 持仓缺因子时回退比率 1（未复权口径）并计入告警。
            valuation_prices: dict[str, float] = {}
            for symbol, position in account.positions.items():
                raw_close = last_closing_prices.get(symbol)
                if raw_close is None:
                    continue
                factor = last_adj_factors.get(symbol)
                if factor is None or factor <= 0 or position.cost_adj_factor <= 0:
                    missing_adj_factor_events += 1
                    valuation_prices[symbol] = raw_close
                else:
                    valuation_prices[symbol] = raw_close * factor / position.cost_adj_factor
            snapshot = account.mark_to_market(trade_date, valuation_prices)
            nav_row = asdict(snapshot)
            if self.benchmark_symbol is not None:
                nav_row["benchmark_equity"] = benchmark_equity.get(trade_date)
            nav_rows.append(nav_row)
            for symbol, position in sorted(account.positions.items()):
                raw_close = last_closing_prices.get(symbol)
                anchored_price = valuation_prices.get(symbol)
                position_rows.append(
                    {
                        "trade_date": trade_date,
                        "symbol": symbol,
                        "quantity": position.quantity,
                        "available_quantity": position.available_quantity,
                        "average_cost": position.average_cost,
                        "close": raw_close,
                        "cost_adj_factor": position.cost_adj_factor,
                        "adj_factor": last_adj_factors.get(symbol),
                        "market_value": position.quantity
                        * (anchored_price if anchored_price is not None else 0.0),
                    }
                )

            # 下单定价：持仓用锚定价（数量换算的正确分母），其余标的用未复权收盘价。
            pricing_map = {**last_closing_prices, **valuation_prices}
            weights = self._position_weights(account, valuation_prices, snapshot.equity)
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
                    closing_prices=pricing_map,
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
                closing_prices=pricing_map,
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
            missing_adj_factor_rows=missing_adj_factor_events,
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
            _benchmark_summary(nav, analytics.summary, self.benchmark_symbol)
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
                "missing_adj_factor_rows": validity.missing_adj_factor_rows,
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

    def _warmup_start_date(self, start_date: date) -> date:
        """按交易日历把加载起点回推 ``warmup_days`` 个交易日。

        回看窗口用日历日近似放宽（交易日约占日历日的 5/7，外加节假日），
        日历不足 warmup_days 时取窗口内最早交易日，无日历数据时
        直接退化为日历日近似——由 get_daily_bars 的日期过滤兜底。
        """

        if self.warmup_days <= 0:
            return start_date
        lookback_start = start_date - timedelta(days=self.warmup_days * 2 + 30)
        calendar = self.repository.get_trade_calendar(
            lookback_start, start_date - timedelta(days=1)
        )
        if calendar.empty:
            return lookback_start
        trading_days = sorted(
            timestamp.date() for timestamp in pd.to_datetime(calendar["cal_date"])
        )
        if len(trading_days) >= self.warmup_days:
            return trading_days[-self.warmup_days]
        return trading_days[0]

    @staticmethod
    def _seed_adj_factors(bars: pd.DataFrame, start_date: date) -> dict[str, float]:
        """Return each symbol's latest valid adjustment factor before ``start_date``."""

        if bars.empty or "adj_factor" not in bars.columns:
            return {}
        factors = pd.to_numeric(bars["adj_factor"], errors="coerce")
        prior = bars[(bars["trade_date"] < pd.Timestamp(start_date)) & factors.gt(0)]
        if prior.empty:
            return {}
        latest = prior.groupby("symbol", observed=True).tail(1)
        return {
            str(symbol): float(factor)
            for symbol, factor in zip(
                latest["symbol"], factors.loc[latest.index], strict=True
            )
        }

    @staticmethod
    def _valid_factors(day_rows: pd.DataFrame) -> dict[str, float]:
        """Return today's positive adjustment factors keyed by symbol."""

        if day_rows.empty or "adj_factor" not in day_rows.columns:
            return {}
        factors = pd.to_numeric(day_rows["adj_factor"], errors="coerce")
        valid = day_rows[factors.gt(0)]
        return {
            str(symbol): float(factor)
            for symbol, factor in zip(valid["symbol"], factors.loc[valid.index], strict=True)
        }

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

    def _benchmark_equity_series(
        self, dates: list[date], initial_cash: float
    ) -> dict[date, float]:
        """Map trade dates to benchmark equity anchored at the first in-range close.

        未配置基准（benchmark_symbol 为空）时返回空字典且 nav 不写该列；
        配置了基准但本地无行情时同样返回空字典，nav 中该列整列为 NA。
        基准当日无行情沿用最近一次收盘价（前向填充）；首条基准行情出现
        之前的交易日保持缺失，锚定后首值恒等于 initial_cash。
        """

        if not self.benchmark_symbol:
            return {}
        bars = self.repository.read_table("benchmark_bars")
        if bars.empty:
            return {}
        selected = bars[bars["symbol"].astype(str).eq(self.benchmark_symbol)]
        if selected.empty:
            return {}
        selected = selected.copy()
        selected["trade_date"] = pd.to_datetime(selected["trade_date"]).dt.normalize()
        selected["raw_close"] = pd.to_numeric(selected["raw_close"], errors="coerce")
        selected = selected.dropna(subset=["raw_close"])
        if selected.empty:
            return {}
        selected = selected[
            selected["trade_date"].between(
                pd.Timestamp(dates[0]), pd.Timestamp(dates[-1])
            )
        ]
        selected = (
            selected.sort_values("trade_date")
            .drop_duplicates("trade_date", keep="last")
        )
        close_by_date = {
            timestamp.date(): float(price)
            for timestamp, price in zip(
                selected["trade_date"], selected["raw_close"], strict=True
            )
        }
        series: dict[date, float] = {}
        first_close: float | None = None
        last_close: float | None = None
        for trade_date in dates:
            close = close_by_date.get(trade_date)
            if close is not None:
                if first_close is None:
                    first_close = close
                last_close = close
            if first_close is not None and last_close is not None and first_close > 0:
                series[trade_date] = initial_cash * last_close / first_close
        return series

    @staticmethod
    def _history_through(bars: pd.DataFrame, trade_date: date) -> pd.DataFrame:
        """Return all bars up to ``trade_date`` using an already-sorted frame."""

        position = bars["trade_date"].searchsorted(pd.Timestamp(trade_date), side="right")
        return bars.iloc[: int(position)]


def _benchmark_summary(
    nav: pd.DataFrame,
    summary: dict[str, object],
    benchmark_symbol: str | None,
) -> dict[str, object]:
    """Attach benchmark return and excess return when benchmark data exists."""

    metrics: dict[str, object] = {}
    if benchmark_symbol:
        metrics["benchmark_symbol"] = benchmark_symbol
    if "benchmark_equity" not in nav.columns:
        return metrics
    benchmark = pd.to_numeric(nav["benchmark_equity"], errors="coerce").dropna()
    if len(benchmark) >= 2 and float(benchmark.iloc[0]) > 0:
        benchmark_return = float(benchmark.iloc[-1]) / float(benchmark.iloc[0]) - 1.0
        metrics["benchmark_return"] = benchmark_return
        cumulative = summary.get("cumulative_return")
        if isinstance(cumulative, (int, float)) and not isinstance(cumulative, bool):
            metrics["excess_return"] = float(cumulative) - benchmark_return
    return metrics
