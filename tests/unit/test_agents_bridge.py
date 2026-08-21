"""AgentRunner 与 decision_to_signal 单元测试（mock LLM，全离线）。

mock LLM 的确定性行为（已实测验证）：对任意 A 股 symbol，
交易员提案恒为 buy / position_pct=0.1 / confidence=0.6，
组合经理恒为 approved / final_position_pct=0.1。
"""

from datetime import date
from pathlib import Path

import pandas as pd

from quant_platform.agents_bridge import AgentRunner, decision_to_signal
from trading_agents.schemas import Decision, TradeProposal
from trading_agents.schemas.models import ApprovalStatus, TradeAction

SYMBOL = "000001.SZ"
TRADE_DATE = date(2024, 4, 26)


def _frame() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=80)
    return pd.DataFrame(
        {
            "symbol": SYMBOL,
            "trade_date": dates,
            "raw_open": 10.0,
            "raw_high": 10.5,
            "raw_low": 9.8,
            "raw_close": 10.2,
            "volume": 1_000_000,
            "amount": 10_200_000.0,
        }
    )


def _runner(tmp_path: Path, use_cache: bool = True) -> AgentRunner:
    return AgentRunner(
        base_dir=tmp_path / "runs",
        cache_dir=tmp_path / "cache",
        use_cache=use_cache,
    )


def _decision(
    status: ApprovalStatus,
    action: TradeAction,
    position_pct: float,
    confidence: float = 0.8,
) -> Decision:
    return Decision(
        ticker=SYMBOL,
        trade_date=TRADE_DATE,
        status=status,
        final_action=action,
        final_position_pct=position_pct,
        proposal=TradeProposal(
            ticker=SYMBOL,
            as_of_date=TRADE_DATE,
            action=action,
            position_pct=position_pct,
            confidence=confidence,
        ),
    )


def test_decide_returns_mock_deterministic_decision(tmp_path: Path) -> None:
    runner = _runner(tmp_path)

    decision = runner.decide(SYMBOL, TRADE_DATE, _frame())

    assert decision.status == ApprovalStatus.APPROVED
    assert decision.final_action == TradeAction.BUY
    assert decision.final_position_pct == 0.1
    assert decision.proposal is not None
    assert decision.proposal.confidence == 0.6


def test_decide_full_returns_pipeline_state_without_cache(tmp_path: Path) -> None:
    runner = _runner(tmp_path)

    state = runner.decide_full(SYMBOL, TRADE_DATE, _frame())

    assert state.decision is not None
    assert len(state.reports) == 4  # 四个分析师维度
    assert state.debate is not None
    assert not (tmp_path / "cache").exists() or not list((tmp_path / "cache").glob("*.json"))


def test_decide_cache_hit_avoids_second_llm_call(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    frame = _frame()

    first = runner.decide(SYMBOL, TRADE_DATE, frame)
    calls_after_first = runner._ctx_base.llm.calls
    cache_files = list((tmp_path / "cache").glob("*.json"))
    assert len(cache_files) == 1

    second = runner.decide(SYMBOL, TRADE_DATE, frame)

    assert runner._ctx_base.llm.calls == calls_after_first  # 未再调用 LLM
    assert second.model_dump() == first.model_dump()


def test_decide_raises_when_history_has_no_data(tmp_path: Path) -> None:
    runner = _runner(tmp_path, use_cache=False)
    frame = _frame()
    early = date(2020, 1, 1)  # 早于全部行情

    try:
        runner.decide(SYMBOL, early, frame)
    except RuntimeError as exc:
        assert SYMBOL in str(exc)
    else:  # pragma: no cover - 不应到达
        raise AssertionError("数据不足时应抛 RuntimeError")


def test_decision_to_signal_approved_buy_clamps_weight() -> None:
    decision = _decision(ApprovalStatus.APPROVED, TradeAction.BUY, 0.5, confidence=0.8)

    signal = decision_to_signal(decision, "s1", TRADE_DATE, SYMBOL, 0.2)

    assert signal is not None
    assert signal.signal_type == "LLM_DECISION"
    assert signal.score == 0.8
    assert signal.target_weight == 0.2  # 被单票上限截断
    assert signal.target_direction == "LONG"


def test_decision_to_signal_conditional_buy_generates_signal() -> None:
    decision = _decision(ApprovalStatus.CONDITIONAL, TradeAction.BUY, 0.1)

    signal = decision_to_signal(decision, "s1", TRADE_DATE, SYMBOL, 0.2)

    assert signal is not None
    assert signal.target_weight == 0.1


def test_decision_to_signal_rejected_returns_none() -> None:
    decision = _decision(ApprovalStatus.REJECTED, TradeAction.BUY, 0.0)

    assert decision_to_signal(decision, "s1", TRADE_DATE, SYMBOL, 0.2) is None


def test_decision_to_signal_hold_returns_none() -> None:
    decision = _decision(ApprovalStatus.APPROVED, TradeAction.HOLD, 0.0)

    assert decision_to_signal(decision, "s1", TRADE_DATE, SYMBOL, 0.2) is None


def test_decision_to_signal_zero_position_returns_none() -> None:
    decision = _decision(ApprovalStatus.APPROVED, TradeAction.BUY, 0.0)

    assert decision_to_signal(decision, "s1", TRADE_DATE, SYMBOL, 0.2) is None
