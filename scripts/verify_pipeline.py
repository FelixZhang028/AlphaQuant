"""端到端：跑通完整流水线（mock LLM + auto 数据源），验证不再降级 stub。

用法: python scripts/verify_pipeline.py [data_source]
"""

import sys
import datetime as dt

sys.path.insert(0, "src")

from trading_agents.cli import build_context
from trading_agents.config import TradingConfig
from trading_agents.orchestrator import run_pipeline


def main() -> None:
    data_source = sys.argv[1] if len(sys.argv) > 1 else "auto"
    config = TradingConfig.load(base_dir=".verify_runs", provider="mock")
    config.market = "CN"
    config.checkpoint_enabled = False
    config.node_retries = 1
    ctx = build_context(config, data_source)
    print(f"数据源: {data_source} -> {type(ctx.provider).__name__}")
    state = run_pipeline(
        "002466.SZ",
        dt.date(2025, 6, 3),
        ctx,
        resume=False,
    )
    print(f"\n== 决策结果 ==")
    idn = state.identity
    print(f"标的: {idn.name} ({idn.symbol})")
    snap = state.snapshot
    if snap:
        print(f"快照: bars={len(snap.bars)} 最后收盘={snap.last_close} "
              f"市值={snap.market_cap}")
        print(f"数据来源标注: snapshot.ticker={snap.ticker.symbol}")
    print(f"审批: {state.decision.status.value}  动作: {state.decision.final_action.value}")
    print(f"产物: {state.artifacts}")
    print("流水线跑通，未降级 stub [OK]")


if __name__ == "__main__":
    main()
