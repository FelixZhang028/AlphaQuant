"""Tests for the AST-based user strategy safety review."""

from __future__ import annotations

from quant_platform.user_strategies.loader import UserStrategyLoader
from quant_platform.user_strategies.safety import check_strategy_source

_CLEAN_STRATEGY = '''
from quant_platform.signals.models import Signal
from quant_platform.user_strategies import BaseStrategy, register_strategy


@register_strategy("clean_demo")
class CleanStrategy(BaseStrategy):
    required_fields = frozenset({"symbol", "trade_date", "adjusted_close"})

    def __init__(self, window: int = 20, name: str = "demo", enabled: bool = True):
        self.window = window
        self.name = name
        self.enabled = enabled

    def generate_signals(self, context):
        history = context.history(fields=["adjusted_close", "is_suspended"], lookback=30)
        history = history[~history["is_suspended"]]
        return [
            Signal(
                strategy_id=self.strategy_id,
                trade_date=context.trade_date,
                symbol="000001.SZ",
                signal_type="CLEAN",
                score=1.0,
            )
        ]
'''


def _codes(issues):
    return {issue.code for issue in issues}


def test_clean_strategy_passes() -> None:
    report = check_strategy_source(_CLEAN_STRATEGY)
    assert not report.blocked
    assert report.blockers == ()
    # 引用了 is_suspended，不应触发 A 股规则提示。
    assert "cn_rules_hint" not in _codes(report.warnings)


def test_blacklisted_import_blocked() -> None:
    report = check_strategy_source("import os\nimport subprocess\n")
    assert report.blocked
    assert _codes(report.blockers) == {"forbidden_import"}
    assert len(report.blockers) == 2


def test_unlisted_import_warns() -> None:
    report = check_strategy_source("import some_random_pkg\n")
    assert not report.blocked
    assert "unlisted_import" in _codes(report.warnings)


def test_forbidden_calls_blocked() -> None:
    report = check_strategy_source('data = eval("1 + 1")\nopen("x.txt")\n')
    assert report.blocked
    assert _codes(report.blockers) == {"forbidden_call"}


def test_shift_negative_blocked() -> None:
    report = check_strategy_source("df['next_close'] = df['close'].shift(-1)\n")
    assert report.blocked
    assert "future_shift" in _codes(report.blockers)


def test_shift_positive_allowed() -> None:
    report = check_strategy_source("df['prev_close'] = df['close'].shift(1)\n")
    assert "future_shift" not in _codes(report.blockers)
    assert not report.blocked


def test_reversed_slice_warns() -> None:
    report = check_strategy_source("latest = series[::-1][0]\n")
    assert not report.blocked
    assert "reversed_slice" in _codes(report.warnings)


def test_missing_param_default_blocked() -> None:
    source = _CLEAN_STRATEGY.replace("window: int = 20", "window: int")
    report = check_strategy_source(source)
    assert report.blocked
    assert "param_missing_default" in _codes(report.blockers)


def test_unknown_required_field_blocked() -> None:
    source = _CLEAN_STRATEGY.replace(
        '{"symbol", "trade_date", "adjusted_close"}',
        '{"symbol", "trade_date", "not_a_field"}',
    )
    report = check_strategy_source(source)
    assert report.blocked
    assert "required_fields_unknown" in _codes(report.blockers)


def test_cn_rules_warning_requires_acknowledgement_semantics() -> None:
    # 未引用 limit/suspend 的策略：不阻止保存，但给出 warning，
    # 页面据此要求用户勾选确认框（report.blocked 为 False 且 warnings 非空）。
    source = _CLEAN_STRATEGY.replace(', "is_suspended"', "").replace(
        "history = history[~history[\"is_suspended\"]]\n        ", ""
    )
    report = check_strategy_source(source)
    assert not report.blocked
    assert "cn_rules_hint" in _codes(report.warnings)


def test_loader_attaches_safety_report() -> None:
    loader = UserStrategyLoader()
    result = loader.load_source(_CLEAN_STRATEGY, label="test")
    assert result.strategies
    assert result.safety_report is not None
    assert not result.safety_report.blocked


def test_loader_reports_safety_on_failure() -> None:
    loader = UserStrategyLoader()
    result = loader.load_source("import os\n", label="test")
    assert not result.strategies
    assert result.errors
    assert result.safety_report is not None
    assert result.safety_report.blocked
