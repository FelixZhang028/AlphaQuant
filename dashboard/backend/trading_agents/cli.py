"""CLI 入口：argparse。

启动即打印免责声明：仅供研究/教学，不构成投资建议，模拟交易不涉及真实资金。

示例：
    python -m trading_agents.cli --ticker AAPL --date 2024-06-01 --llm mock
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from trading_agents.config import TradingConfig
from trading_agents.data.stub import StubDataProvider
from trading_agents.execution import SimulatedExchange
from trading_agents.llm import create_llm_client
from trading_agents.memory import MemoryStore
from trading_agents.orchestrator import PipelineContext, run_pipeline

DISCLAIMER = (
    "免责声明：本框架仅供研究与教学用途，所有输出不构成任何投资建议；"
    "全部为模拟交易，不涉及真实资金。市场有风险，决策需自负。"
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="trading_agents",
        description="多智能体 LLM 量化交易框架（研究/教学，模拟交易）",
    )
    p.add_argument("--ticker", default=None, help="标的代码，如 AAPL（缺省时进入 TUI）")
    p.add_argument("--date", default=None, help="分析日期 YYYY-MM-DD（缺省时进入 TUI）")
    p.add_argument("--tui", action="store_true", help="启动实时 TUI 界面")
    p.add_argument("--llm", default=None,
                   help="LLM provider: mock/openai/deepseek/qwen/glm/ollama")
    p.add_argument("--model", default=None,
                   help="LLM 模型名（默认按 provider 自动选择，如 deepseek 用 deepseek-chat）")
    p.add_argument("--data", default="stub",
                   choices=["stub", "yfinance", "eastmoney", "akshare", "tonghuashun", "auto"],
                   help="数据源：stub=离线合成(默认) / yfinance=美股 / eastmoney=A股东财 / "
                        "akshare=A股akshare / tonghuashun=A股同花顺 / auto=多源自动降级")
    p.add_argument("--market", default="CN", help="市场，默认 CN")
    p.add_argument("--base-dir", default=None, help="运行产物根目录（默认 ./runs）")
    p.add_argument("--debate-rounds", type=int, default=None, help="辩论轮数，默认 2")
    p.add_argument("--proxy", default=None,
                   help="行情数据源代理，如 http://127.0.0.1:7897；传空字符串禁用")
    p.add_argument("--no-resume", action="store_true", help="忽略 checkpoint 重新运行")
    p.add_argument("--debug", action="store_true", help="逐节点 trace 打印")
    return p


def build_context(config: TradingConfig, data_source: str) -> PipelineContext:
    """装配流水线上下文（CLI 与 TUI 共用）。配置错误抛 KeyError/RuntimeError。"""
    llm = create_llm_client(
        config.llm.provider,
        model=config.llm.deep_think_model,
        base_url=config.llm.base_url,
        env_key_name=TradingConfig.env_key_name(config.llm.provider),
    )
    if data_source == "yfinance":
        from trading_agents.data.yfinance_provider import YFinanceProvider

        provider = YFinanceProvider(cache_path=config.sqlite_path, proxy=config.http_proxy)
    elif data_source == "eastmoney":
        from trading_agents.data.eastmoney import EastMoneyProvider

        provider = EastMoneyProvider(cache_path=config.sqlite_path)
    elif data_source == "akshare":
        from trading_agents.data.akshare_provider import AkshareProvider

        provider = AkshareProvider(cache_path=config.sqlite_path)
    elif data_source == "tonghuashun":
        from trading_agents.data.tonghuashun import TonghuashunProvider

        provider = TonghuashunProvider(cache_path=config.sqlite_path)
    elif data_source == "auto":
        from trading_agents.data.akshare_provider import AkshareProvider
        from trading_agents.data.eastmoney import EastMoneyProvider
        from trading_agents.data.fallback import FallbackProvider
        from trading_agents.data.tonghuashun import TonghuashunProvider

        provider = FallbackProvider(
            [
                EastMoneyProvider(cache_path=config.sqlite_path),
                AkshareProvider(cache_path=config.sqlite_path),
                TonghuashunProvider(cache_path=config.sqlite_path),
            ]
        )
    else:
        provider = StubDataProvider()
    return PipelineContext(
        config=config,
        llm=llm,
        provider=provider,
        memory=MemoryStore(config.sqlite_path, config.memory_dir),
        exchange=SimulatedExchange(config.execution),
    )


def main(argv: list[str] | None = None) -> int:
    print(DISCLAIMER, file=sys.stderr)
    args = build_parser().parse_args(argv)

    # --tui 或未提供 ticker/date 时进入实时 TUI（向后兼容全参数模式）
    if args.tui or not args.ticker or not args.date:
        from trading_agents.tui import run_tui

        return run_tui()

    try:
        trade_date = dt.date.fromisoformat(args.date)
    except ValueError:
        print(f"错误：--date 格式应为 YYYY-MM-DD，收到 {args.date!r}", file=sys.stderr)
        return 2

    config = TradingConfig.load(base_dir=args.base_dir, provider=args.llm, debug=args.debug)
    config.market = args.market
    if args.debate_rounds is not None:
        config.debate_rounds = args.debate_rounds
    if args.proxy is not None:
        config.http_proxy = args.proxy or None
    if args.model is not None:
        config.llm.deep_think_model = args.model
        config.llm.quick_think_model = args.model

    try:
        ctx = build_context(config, args.data)
    except (KeyError, RuntimeError) as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 2

    try:
        state = run_pipeline(
            args.ticker, trade_date, ctx, resume=not args.no_resume
        )
    except RuntimeError as exc:
        print(f"流水线失败：{exc}", file=sys.stderr)
        return 1

    decision = state.decision
    print(f"\n== 决策结果 {args.ticker} @ {trade_date} ==")
    if state.identity is not None:
        idn = state.identity
        print(f"标的: {idn.name} ({idn.symbol})  行业: {idn.industry or '-'}  货币: {idn.currency}")
    if state.snapshot is not None and state.snapshot.market_cap:
        print(f"总市值: {state.snapshot.market_cap:,.0f} {idn.currency if state.identity else ''}"
              f"  最新收盘: {state.snapshot.last_close}")
    if decision is not None:
        print(f"审批: {decision.status.value}  动作: {decision.final_action.value}  "
              f"仓位: {decision.final_position_pct:.1%}")
        if decision.rejection_reason:
            print(f"驳回原因: {decision.rejection_reason}")
        for link in decision.rationale_chain:
            print(f"  理由链: {link}")
    if state.fill is not None:
        f = state.fill
        print(f"成交: {f.action.value} {f.quantity} @ {f.price} "
              f"(滑点 {f.slippage}, 手续费 {f.commission}, 交收 {f.settlement_date})")
    else:
        print("成交: 无（被驳回或 hold）")
    print(f"产物: {state.artifacts}")
    print(f"trace: {config.trace_dir / (state.run_id + '.jsonl')}")
    print(DISCLAIMER, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
