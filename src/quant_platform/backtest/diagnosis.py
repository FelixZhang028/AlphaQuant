"""Plain-language diagnosis for one completed backtest.

生成面向非专业用户的通俗简体中文解读：盈亏来源、关键时期、
胜率结构、交易成本、基准对比和启发式调参建议。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd

from quant_platform.backtest.analytics import build_closed_trades
from quant_platform.backtest.metrics import calculate_monthly_returns
from quant_platform.backtest.result import BacktestResult


@dataclass(frozen=True)
class DiagnosisSection:
    """One titled group of plain-language bullets."""

    title: str
    bullets: list[str]


@dataclass(frozen=True)
class DiagnosisReport:
    """Full plain-language diagnosis for one backtest result."""

    sections: list[DiagnosisSection]


def generate_diagnosis(result: BacktestResult) -> DiagnosisReport:
    """Build the plain-language diagnosis; missing data degrades gracefully."""

    summary = result.summary if isinstance(result.summary, dict) else {}
    trades = result.trades if not result.trades.empty else _safe_closed_trades(result.fills)

    sections = [
        _diagnose_pnl_source(summary, trades),
        _diagnose_periods(result.nav),
        _diagnose_win_rate(summary),
        _diagnose_costs(summary),
        _diagnose_benchmark(result, summary),
        _diagnose_suggestions(summary, trades, result.nav),
    ]
    return DiagnosisReport(sections=sections)


def _safe_closed_trades(fills: pd.DataFrame) -> pd.DataFrame:
    if fills.empty:
        return pd.DataFrame()
    try:
        return build_closed_trades(fills)
    except (ValueError, KeyError):
        return pd.DataFrame()


def _num(summary: dict[str, Any], key: str) -> float | None:
    value = summary.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _money(value: float) -> str:
    return f"{value:,.2f} 元"


def _percent(value: float) -> str:
    return f"{value:.2%}"


def _diagnose_pnl_source(
    summary: dict[str, Any], trades: pd.DataFrame
) -> DiagnosisSection:
    bullets: list[str] = []
    cumulative_return = _num(summary, "cumulative_return")
    final_equity = _num(summary, "final_equity")
    initial_cash = _num(summary, "initial_cash")
    if cumulative_return is not None:
        direction = "盈利" if cumulative_return >= 0 else "亏损"
        bullets.append(f"本次回测整体{direction} {_percent(abs(cumulative_return))}。")
    if initial_cash is not None and final_equity is not None:
        change = final_equity - initial_cash
        word = "赚了" if change >= 0 else "亏了"
        bullets.append(f"初始资金 {_money(initial_cash)}，结束时 {_money(final_equity)}，"
                       f"合计{word} {_money(abs(change))}。")

    if trades.empty or "net_pnl" not in trades.columns:
        bullets.append("没有已完成的买卖配对，暂时无法拆解盈利/亏损来自哪些股票。")
        return DiagnosisSection(title="为什么盈利/亏损", bullets=bullets)

    by_symbol = trades.groupby("symbol", observed=True)["net_pnl"].sum().sort_values(
        ascending=False
    )
    winners = by_symbol[by_symbol > 0].head(3)
    losers = by_symbol[by_symbol < 0].tail(3).sort_values()
    if winners.empty and losers.empty:
        bullets.append("所有完整交易合计基本打平，没有明显的盈利或亏损来源。")
    for symbol, pnl in winners.items():
        bullets.append(f"赚钱最多：{symbol}，贡献了 {_money(float(pnl))} 净利润。")
    for symbol, pnl in losers.items():
        bullets.append(f"亏钱最多：{symbol}，亏掉了 {_money(abs(float(pnl)))}。")
    return DiagnosisSection(title="为什么盈利/亏损", bullets=bullets)


def _diagnose_periods(nav: pd.DataFrame) -> DiagnosisSection:
    monthly = calculate_monthly_returns(nav)
    if monthly.empty:
        return DiagnosisSection(
            title="哪些时期影响最大",
            bullets=["净值数据不足，暂时无法判断哪段时期影响最大。"],
        )
    best = monthly.loc[monthly["return"].idxmax()]
    worst = monthly.loc[monthly["return"].idxmin()]
    bullets = [
        f"表现最好的月份是 {best['month']}，当月收益 {_percent(float(best['return']))}。",
        f"表现最差的月份是 {worst['month']}，当月收益 {_percent(float(worst['return']))}。",
    ]
    return DiagnosisSection(title="哪些时期影响最大", bullets=bullets)


def _diagnose_win_rate(summary: dict[str, Any]) -> DiagnosisSection:
    closed = _num(summary, "closed_trades")
    win_rate = _num(summary, "trade_win_rate")
    if closed is None or closed <= 0 or win_rate is None:
        return DiagnosisSection(
            title="胜率与盈亏结构",
            bullets=["没有足够完成交易，暂时无法分析胜率与盈亏结构。"],
        )
    average_win = _num(summary, "average_win")
    average_loss = _num(summary, "average_loss")
    payoff = _num(summary, "payoff_ratio")

    bullets = [f"一共完成 {int(closed)} 笔交易，胜率 {_percent(win_rate)}。"]
    if average_win is not None:
        bullets.append(f"盈利的交易平均每笔赚 {_money(average_win)}。")
    if average_loss is not None:
        bullets.append(f"亏损的交易平均每笔亏 {_money(abs(average_loss))}。")
    if payoff is not None:
        bullets.append(f"盈亏比（平均盈利÷平均亏损）为 {payoff:.2f}。")

    net = _num(summary, "realized_net_pnl")
    if average_win is not None and average_loss is not None and abs(average_loss) > 0:
        if win_rate >= 0.5 and net is not None and net < 0:
            bullets.append(
                f"胜率 {_percent(win_rate)} 不算低，但平均每笔亏损大于盈利，"
                "说明止损偏慢、小赚大亏，这是亏钱的主要原因。"
            )
        elif win_rate < 0.5 and net is not None and net > 0:
            bullets.append(
                f"胜率只有 {_percent(win_rate)}，但平均每笔盈利明显大于亏损，"
                "属于少赚次数、多赚幅度的风格，整体仍然赚钱。"
            )
        elif payoff is not None and payoff >= 1.0:
            bullets.append("平均每笔盈利不小于平均亏损，盈亏结构比较健康。")
        else:
            bullets.append("平均每笔盈利小于平均亏损，需要靠较高的胜率才能维持盈利。")
    return DiagnosisSection(title="胜率与盈亏结构", bullets=bullets)


def _diagnose_costs(summary: dict[str, Any]) -> DiagnosisSection:
    total_cost = _num(summary, "total_transaction_cost")
    if total_cost is None:
        return DiagnosisSection(
            title="交易成本损失",
            bullets=["结果中没有成本数据，暂时无法评估交易成本的影响。"],
        )
    commission = _num(summary, "commission") or 0.0
    stamp_tax = _num(summary, "stamp_tax") or 0.0
    slippage = _num(summary, "slippage_cost") or 0.0
    initial_cash = _num(summary, "initial_cash")
    gross_pnl = _num(summary, "realized_gross_pnl")

    bullets = [
        f"全程交易成本合计 {_money(total_cost)}"
        f"（佣金 {_money(commission)}、印花税 {_money(stamp_tax)}、滑点 {_money(slippage)}）。"
    ]
    if initial_cash is not None and initial_cash > 0:
        bullets.append(f"成本占初始资金的 {_percent(total_cost / initial_cash)}。")
    if gross_pnl is not None and gross_pnl > 0:
        bullets.append(f"成本吃掉了毛收益的 {_percent(total_cost / gross_pnl)}。")
    elif gross_pnl is not None and gross_pnl <= 0 and total_cost > 0:
        bullets.append("毛收益本身就没有赚钱，交易成本进一步放大了亏损。")
    return DiagnosisSection(title="交易成本损失", bullets=bullets)


def _diagnose_benchmark(result: BacktestResult, summary: dict[str, Any]) -> DiagnosisSection:
    title = "与沪深300对比"
    nav = result.nav
    if not nav.empty and "benchmark_equity" in nav.columns:
        benchmark = pd.to_numeric(nav["benchmark_equity"], errors="coerce").dropna()
        if len(benchmark) >= 2 and float(benchmark.iloc[0]) > 0:
            benchmark_return = float(benchmark.iloc[-1]) / float(benchmark.iloc[0]) - 1.0
            strategy_return = _num(summary, "cumulative_return")
            bullets = [f"同期沪深300基准收益为 {_percent(benchmark_return)}。"]
            if strategy_return is not None:
                excess = strategy_return - benchmark_return
                if excess >= 0:
                    bullets.append(
                        f"策略跑赢基准 {_percent(excess)}，这段时间表现好于大盘。"
                    )
                else:
                    bullets.append(
                        f"策略跑输基准 {_percent(abs(excess))}，这段时间不如直接持有大盘。"
                    )
            return DiagnosisSection(title=title, bullets=bullets)
    return DiagnosisSection(
        title=title,
        bullets=[
            "未配置沪深300基准数据，本次结果无法与大盘对比。"
            "后续配置基准后即可看到超额收益评价。"
        ],
    )


def _diagnose_suggestions(
    summary: dict[str, Any], trades: pd.DataFrame, nav: pd.DataFrame
) -> DiagnosisSection:
    suggestions: list[str] = []

    cost_ratio = _num(summary, "transaction_cost_to_initial_cash")
    if cost_ratio is not None and cost_ratio > 0.03:
        suggestions.append(
            "建议：交易成本占初始资金比例偏高，可尝试降低调仓频率或减少交易次数。"
        )

    max_drawdown = _num(summary, "max_drawdown")
    max_weight = _num(summary, "max_single_position_weight")
    average_positions = _num(summary, "average_position_count")
    if max_drawdown is not None and max_drawdown <= -0.2:
        if max_weight is not None and max_weight > 0.3:
            suggestions.append(
                "建议：最大回撤较深且单股权重较高，可尝试降低单只股票的资金占比。"
            )
        elif average_positions is not None and average_positions < 3:
            suggestions.append(
                "建议：最大回撤较深且持股数量偏少，可尝试增加持仓数量以分散风险。"
            )
        else:
            suggestions.append(
                "建议：最大回撤较深，可尝试收紧止损规则或降低整体仓位。"
            )

    closed = _num(summary, "closed_trades")
    if closed is not None and 0 < closed < 30:
        suggestions.append(
            f"建议：完整交易只有 {int(closed)} 笔，样本偏少，结论可能偶然，"
            "可尝试延长回测区间再观察。"
        )
    elif closed is not None and closed == 0:
        suggestions.append(
            "建议：没有产生完整买卖，可检查策略信号是否过于严格，或延长回测区间。"
        )

    win_rate = _num(summary, "trade_win_rate")
    average_win = _num(summary, "average_win")
    average_loss = _num(summary, "average_loss")
    if (
        win_rate is not None
        and win_rate >= 0.5
        and average_win is not None
        and average_loss is not None
        and abs(average_loss) > average_win
    ):
        suggestions.append(
            "建议：胜率不低但亏多赚少，可尝试收紧止损条件，避免单笔亏损过大。"
        )

    if not suggestions:
        suggestions.append("建议：本次结果未发现突出的问题点，可在更长区间或不同参数下复核。")
    return DiagnosisSection(title="可优先调整的参数建议", bullets=suggestions[:4])
