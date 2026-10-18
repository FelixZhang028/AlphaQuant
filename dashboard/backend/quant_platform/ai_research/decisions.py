"""Questions for the decision model Jev, asked about data the platform already has.

Jev answers typed questions with probabilities instead of text. Two uses:

- AI researcher: the lean of one stock (偏多 / 中性 / 偏空) as probabilities, from the same facts
  table the chat model read, so the page can show a second, independent estimate.
- Backtest review: how risky the strategy is (five levels) and how likely the result is to fail on
  new data (overfitting or luck), from the run's own numbers and validity warnings.

The state sent is exactly the rows shown on the page, so a user can see what the model saw.
"""

from __future__ import annotations

from typing import Any

from quant_platform.ai_research.facts import Fact, StockFacts
from quant_platform.jev import choice_question, noul_question, score_question

TILT_QUESTION = choice_question(
    "只根据 state 里的数据，这只股票接下来一段时间的整体倾向是什么？不要考虑 state 以外的任何信息。",
    {
        "偏多": "数据里支持上涨的因素明显多于风险",
        "中性": "支持上涨的因素和风险大致相当，或者数据不足以判断",
        "偏空": "数据里的风险明显多于支持上涨的因素",
    },
)
RISK_LEVELS = ["低风险", "中低风险", "中等风险", "中高风险", "高风险"]
REVIEW_QUESTIONS = {
    "risk": score_question(
        "只根据 state 里的回测数据，这个策略的风险有多高？主要看最大回撤、收益波动、持股集中度、交易成本和有效性警告。",
        RISK_LEVELS,
    ),
    "overfit": noul_question(
        "只根据 state 里的回测数据，这个回测结果是否很可能在新的数据上做不到（过度拟合或者依赖巧合）？",
        "很可能做不到：例如交易次数少、回测时间短、只做过样本内回测、收益远好于基准却没有合理来源、或者有严重的有效性警告",
        "不太可能：交易次数多、回测时间足够长、和基准相比表现合理、没有严重的有效性警告",
    ),
}
REBALANCE_NAMES = {"daily": "每日", "weekly": "每周", "monthly": "每月"}
VALIDITY_NAMES = {"OK": "通过", "PASS": "通过", "WARNING": "有警告", "ERROR": "有错误"}


def model_name(client: Any) -> str:
    """The version that answered (``jev-1.13.0``), else the requested name, without the provider prefix."""

    return str(getattr(client, "served_model", None) or client.model).split("/")[-1]


def stock_state(stock: StockFacts) -> dict[str, Any]:
    return {
        "股票": f"{stock.name}（{stock.symbol}）",
        "数据截至": stock.trade_date.isoformat(),
        "数据": {fact.label: f"{fact.text}（{fact.as_of}）" for fact in stock.facts},
        "本地缺少的数据": [f"{item['group']}：{item['reason']}" for item in stock.missing],
    }


def tilt_odds(client: Any, stock: StockFacts) -> dict[str, Any]:
    """``{choice, probabilities, confidence, model}`` for the stock's lean."""

    answer = client.ask(stock_state(stock), {"tilt": TILT_QUESTION})["tilt"]
    return {"choice": answer["choice"], "probabilities": answer["probabilities"], "confidence": answer["confidence"],
            "model": model_name(client)}


def _pct(value: Any) -> str:
    return f"{float(value):.2f}%"


def backtest_facts(run: dict[str, Any], result: dict[str, Any], benchmark: dict[str, Any] | None) -> list[Fact]:
    """The rows sent to the model and shown on the page. Percent fields of ``result`` are already in percent."""

    rows: list[Fact] = []

    def add(key: str, group: str, label: str, text: str, value: float | None = None) -> None:
        rows.append(Fact(key, group, label, text, value))

    config = result.get("effective_config") or {}
    days = len(result.get("nav_dates") or [])
    add("period", "回测设置", "回测区间", f"{run.get('from_date')} 至 {run.get('to_date')}（{days} 个交易日）", float(days))
    if config.get("market"):
        add("market", "回测设置", "股票范围", str(config["market"]))
    if config.get("max_positions"):
        add("max_positions", "回测设置", "最多持股", f"{config['max_positions']} 只", float(config["max_positions"]))
    if config.get("rebalance"):
        add("rebalance", "回测设置", "调仓频率", REBALANCE_NAMES.get(config["rebalance"], str(config["rebalance"])))
    add("parameters", "回测设置", "策略参数个数", f"{len(config.get('strategy_parameters') or {})} 个")
    for key, label in (("total_return", "总收益"), ("annual_return", "年化收益"), ("max_drawdown", "最大回撤")):
        if result.get(key) is not None:
            add(key, "收益与风险", label, _pct(result[key]), float(result[key]))
    if result.get("sharpe") is not None:
        add("sharpe", "收益与风险", "夏普比率", f"{float(result['sharpe']):.2f}", float(result["sharpe"]))
    if result.get("win_rate") is not None:
        add("win_rate", "收益与风险", "上涨的交易日占比", _pct(result["win_rate"]), float(result["win_rate"]))
    trades = result.get("trades") or []
    add("fills", "交易", "成交笔数", f"{int(result.get('fills') or len(trades))} 笔", float(result.get("fills") or len(trades)))
    if result.get("closed_trades") is not None:
        add("closed_trades", "交易", "完整买卖次数", f"{int(result['closed_trades'])} 次", float(result["closed_trades"]))
    if result.get("trade_win_rate") is not None:
        add("trade_win_rate", "交易", "赚钱的买卖占比", _pct(result["trade_win_rate"]), float(result["trade_win_rate"]))
    if result.get("average_holding_days") is not None:
        add("holding_days", "交易", "平均持有天数", f"{float(result['average_holding_days']):.0f} 天", float(result["average_holding_days"]))
    capital = config.get("initial_capital")
    if result.get("total_cost") is not None and capital:
        share = float(result["total_cost"]) / float(capital) * 100
        add("cost", "交易", "交易成本占初始资金", f"{share:.2f}%", share)
    if trades:
        stocks = len({trade.get("symbol") for trade in trades})
        add("stocks", "交易", "交易过的股票", f"{stocks} 只", float(stocks))
    if benchmark and benchmark.get("comparable"):
        name = benchmark.get("name") or benchmark.get("symbol")
        for key, label in (("benchmark_return", f"{name} 同期收益"), ("excess_return", "超额收益"),
                           ("benchmark_max_drawdown", f"{name} 同期最大回撤")):
            if benchmark.get(key) is not None:
                add(key, "和基准比较", label, _pct(benchmark[key]), float(benchmark[key]))
        if benchmark.get("beta") is not None:
            add("beta", "和基准比较", "Beta（相对基准的波动）", f"{float(benchmark['beta']):.2f}", float(benchmark["beta"]))
    status = result.get("validity_status")
    if status:
        add("validity", "有效性检查", "检查结果", VALIDITY_NAMES.get(status, str(status)))
    for i, issue in enumerate(result.get("validity_issues") or [], start=1):
        level = "错误" if issue.get("severity") == "ERROR" else "警告"
        add(f"issue_{i}", "有效性检查", level, str(issue.get("message", "")))
    return rows


def review_backtest(client: Any, rows: list[Fact]) -> dict[str, Any]:
    state = {"回测数据": [f"{row.group} · {row.label}：{row.text}" for row in rows]}
    answers = client.ask(state, REVIEW_QUESTIONS)
    risk = answers["risk"]
    return {
        "risk": {"level": RISK_LEVELS[min(len(RISK_LEVELS) - 1, max(0, round(risk["score"])))], "score": risk["score"],
                 "probabilities": risk["probabilities"], "confidence": risk["confidence"]},
        "overfit": {"probability": answers["overfit"]["probability"]},
        "model": model_name(client),
    }
