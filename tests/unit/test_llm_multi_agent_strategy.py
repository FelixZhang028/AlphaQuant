"""llm_multi_agent 策略插件单元测试（mock LLM，全离线）。

mock LLM 对任意 symbol 恒产出 approved / buy / final_position_pct=0.1，
因此每只候选标的都会生成 target_weight=min(0.1, 上限) 的信号。
"""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from quant_platform.strategies.context import StrategyContext
from quant_platform.strategies.llm_multi_agent import LLMMultiAgentStrategy

SYMBOLS = ("000001.SZ", "600000.SH", "000002.SZ")
TRADE_DATE = date(2024, 4, 26)

PARAMETERS = {
    "llm_provider": "mock",
    "debate_rounds": 1,
    "lookback_days": 60,
    "max_candidates": 10,
    "max_weight_per_stock": 0.2,
    "use_cache": True,
}


def _history(periods: int = 80) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=periods)
    frames = []
    for index, symbol in enumerate(SYMBOLS):
        frames.append(
            pd.DataFrame(
                {
                    "symbol": symbol,
                    "trade_date": dates,
                    "raw_open": 10.0,
                    "raw_high": 10.5,
                    "raw_low": 9.8,
                    "raw_close": 10.0 + index,
                    "volume": 1_000_000,
                    "amount": 10_000_000.0 * (index + 1),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


@pytest.fixture()
def strategy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LLMMultiAgentStrategy:
    # 把 runtime 产物与缓存隔离到 tmp_path
    monkeypatch.chdir(tmp_path)
    return LLMMultiAgentStrategy.from_parameters("llm_test_v1", PARAMETERS)


def test_generate_signals_with_mock_llm(
    strategy: LLMMultiAgentStrategy,
) -> None:
    context = StrategyContext.create(TRADE_DATE, _history(), SYMBOLS)

    signals = strategy.generate_signals(context)

    assert {signal.symbol for signal in signals} == set(SYMBOLS)
    for signal in signals:
        assert signal.strategy_id == "llm_test_v1"
        assert signal.trade_date == TRADE_DATE
        assert signal.signal_type == "LLM_DECISION"
        assert signal.target_weight is not None
        assert signal.target_weight <= PARAMETERS["max_weight_per_stock"]
        assert signal.target_weight == pytest.approx(0.1)
        assert signal.score == pytest.approx(0.6)  # mock 提案 confidence


def test_max_candidates_limits_signals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    parameters = {**PARAMETERS, "max_candidates": 2}
    strategy = LLMMultiAgentStrategy.from_parameters("llm_test_v1", parameters)
    context = StrategyContext.create(TRADE_DATE, _history(), SYMBOLS)

    signals = strategy.generate_signals(context)

    assert len(signals) == 2
    # 成交额最大的是 000002.SZ 与 600000.SH
    assert {signal.symbol for signal in signals} == {"000002.SZ", "600000.SH"}


def test_no_future_data_leakage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    strategy = LLMMultiAgentStrategy.from_parameters(
        "llm_test_v1", {**PARAMETERS, "use_cache": False}
    )
    history = _history()
    context = StrategyContext.create(TRADE_DATE, history, SYMBOLS)
    baseline = strategy.generate_signals(context)

    # 篡改 trade_date 之后的行情（价格翻倍），信号必须不变
    tampered = history.copy()
    future = pd.to_datetime(tampered["trade_date"]) > pd.Timestamp(TRADE_DATE)
    tampered.loc[future, ["raw_open", "raw_high", "raw_low", "raw_close"]] = 999.0
    # 追加更远的未来行
    extra = history[history["symbol"] == "000001.SZ"].tail(3).copy()
    extra["trade_date"] = pd.bdate_range("2024-05-06", periods=3)
    extra["raw_close"] = 888.0
    tampered = pd.concat([tampered, extra], ignore_index=True)

    context2 = StrategyContext.create(TRADE_DATE, tampered, SYMBOLS)
    rerun = LLMMultiAgentStrategy.from_parameters(
        "llm_test_v1", {**PARAMETERS, "use_cache": False}
    )
    signals2 = rerun.generate_signals(context2)

    assert signals2 == baseline
