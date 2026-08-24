"""首页新手引导：把「数据更新 → 股票池 → 创建策略 → 回测 → 查看结果 → 模拟交易」
做成分步向导（反馈第 1 条）。

本模块只包含纯逻辑（步骤状态推导），渲染在 ``welcome.py`` 中完成，
便于单元测试。步骤状态来自就绪度报告、策略包存储、回测记录与模拟账户，
全部本地读取、无网络访问。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class StepState(StrEnum):
    DONE = "done"
    CURRENT = "current"
    TODO = "todo"


@dataclass(frozen=True)
class GuideStep:
    """向导中的一个步骤。"""

    key: str
    title: str
    hint: str
    page: str
    action: str
    state: StepState


def build_guide_steps(
    *,
    configured_symbols: int,
    symbols_with_sufficient_history: int,
    has_strategies: bool,
    has_backtest_runs: bool,
    has_paper_accounts: bool,
) -> tuple[GuideStep, ...]:
    """按反馈顺序推导六个步骤的状态。

    规则：已完成 -> done；第一个未完成的 -> current（建议下一步）；
    其余 -> todo。数据更新以「配置的股票全部有足够历史」为完成标准。
    """

    data_done = configured_symbols > 0 and (
        symbols_with_sufficient_history >= configured_symbols
    )
    flags = [
        data_done,
        configured_symbols > 0,
        has_strategies,
        has_backtest_runs,
        has_backtest_runs,
        has_paper_accounts,
    ]
    specs = [
        ("data", "① 数据更新", "下载证券主表与行情，覆盖配置的股票池",
         "pages/1_data_management.py", "去更新数据"),
        ("universe", "② 股票池", "添加要研究的股票代码",
         "pages/5_universe_management.py", "去配置股票池"),
        ("strategy", "③ 创建策略", "用模板、积木或自然语言创建一个策略",
         "pages/0_strategy_hub.py", "去创建策略"),
        ("backtest", "④ 回测", "选择策略运行一次完整回测",
         "home.py", "去运行回测"),
        ("review", "⑤ 查看结果", "查看收益、回撤、通俗诊断与可信度审计",
         "pages/6_run_library.py", "去查看结果"),
        ("paper", "⑥ 模拟交易", "通过上线前检查后启动模拟账户",
         "pages/4_paper_trading.py", "去模拟交易"),
    ]
    first_open = next((i for i, done in enumerate(flags) if not done), None)
    steps: list[GuideStep] = []
    for index, (key, title, hint, page, action) in enumerate(specs):
        if flags[index]:
            state = StepState.DONE
        elif index == first_open:
            state = StepState.CURRENT
        else:
            state = StepState.TODO
        steps.append(GuideStep(key, title, hint, page, action, state))
    return tuple(steps)
