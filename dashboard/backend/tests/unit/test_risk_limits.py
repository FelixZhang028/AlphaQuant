"""Target-portfolio risk limits: what is fitted inside the limits, what is still rejected, and how a run reports it."""
from datetime import date

import pandas as pd
import pytest

from quant_platform.backtest.validity import assess_backtest_validity
from quant_platform.portfolio.models import TargetPosition
from quant_platform.risk.basic_rules import RiskDecision, evaluate_target_risk
from quant_platform.risk.config import RiskLimits

DAY = date(2024, 1, 31)


def targets(*weights):
    return [TargetPosition("s", DAY, f"00000{index}.SZ", weight) for index, weight in enumerate(weights, start=1)]


def weights(evaluation):
    return {target.symbol: round(target.target_weight, 6) for target in evaluation.targets}


def test_holding_few_stocks_under_a_single_stock_cap_keeps_the_rest_in_cash():
    # 以前：平均分配 50%/50% 超过 30% 的上限，整个目标被拒绝，回测一笔都不下。
    result = evaluate_target_risk(targets(0.5, 0.5), RiskLimits(max_single_weight=0.3))
    assert result.decision == RiskDecision.ADJUST
    assert weights(result) == {"000001.SZ": 0.3, "000002.SZ": 0.3}
    assert result.reasons == ("单只股票权重超过 30%，超出的部分留作现金",)
    assert result.max_weight == 0.5                                   # 记录的是策略原来的目标


def test_a_portfolio_over_the_total_cap_is_scaled_down():
    result = evaluate_target_risk(targets(0.25, 0.25, 0.25, 0.25), RiskLimits(max_total_weight=0.8, max_single_weight=0.3))
    assert result.decision == RiskDecision.ADJUST and sum(weights(result).values()) == pytest.approx(0.8)
    assert result.reasons == ("总仓位超过 80%，按比例降低",)
    untouched = evaluate_target_risk(targets(0.2, 0.2), RiskLimits(max_single_weight=0.3))
    assert untouched.decision == RiskDecision.PASS and untouched.reasons == () and weights(untouched) == {"000001.SZ": 0.2, "000002.SZ": 0.2}


def test_after_the_drawdown_line_each_action_does_what_it_says():
    held = {"000001.SZ": 0.15, "000009.SZ": 0.4}
    reduce = evaluate_target_risk(targets(0.25, 0.25, 0.25, 0.25), RiskLimits(drawdown_action="reduce", drawdown_target_weight=0.5),
                                  current_drawdown=-0.21, current_weights=held)
    # 降低仓位：继续调仓（换成新的股票），总仓位不超过 50%。
    assert reduce.decision == RiskDecision.ADJUST and sum(weights(reduce).values()) == pytest.approx(0.5) and len(weights(reduce)) == 4
    assert "继续调仓，总仓位不超过 50%" in reduce.reasons[0]
    stop = evaluate_target_risk(targets(0.25, 0.25), RiskLimits(drawdown_action="stop_new"), current_drawdown=-0.2, current_weights=held)
    # 停止新开仓：不买新股票，已有的最多保持现在的仓位；策略不要的已有持仓照常卖出。
    assert stop.decision == RiskDecision.ADJUST and weights(stop) == {"000001.SZ": 0.15}
    assert "不买入新股票" in stop.reasons[0]
    liquidate = evaluate_target_risk(targets(0.25, 0.25), RiskLimits(drawdown_action="liquidate"), current_drawdown=-0.3)
    assert liquidate.decision == RiskDecision.REJECT and liquidate.targets == () and "已清仓" in liquidate.reasons[0]
    before = evaluate_target_risk(targets(0.25, 0.25), RiskLimits(drawdown_action="liquidate"), current_drawdown=-0.19)
    assert before.decision == RiskDecision.PASS


def test_what_holding_less_cannot_fix_is_still_rejected():
    assert evaluate_target_risk(targets(0.5, -0.1), RiskLimits()).decision == RiskDecision.REJECT
    too_many = evaluate_target_risk(targets(*[0.1] * 4), RiskLimits(max_positions=3))
    assert too_many.decision == RiskDecision.REJECT and too_many.reasons == ("持仓数量超过 3 只",)
    industry = evaluate_target_risk(targets(0.3, 0.3), RiskLimits(max_industry_weight=0.4, max_single_weight=0.3),
                                    industry_map={"000001.SZ": "银行", "000002.SZ": "银行"})
    assert industry.decision == RiskDecision.REJECT and "行业集中度超过限制" in industry.reasons
    off = evaluate_target_risk(targets(0.9, 0.9), RiskLimits(enabled=False))
    assert off.decision == RiskDecision.PASS and weights(off) == {"000001.SZ": 0.9, "000002.SZ": 0.9}


def test_a_run_says_how_often_the_limits_changed_or_stopped_a_rebalance_and_since_when():
    nav = pd.DataFrame({"trade_date": pd.bdate_range("2024-01-02", periods=5), "nav": 1.0})
    interventions = [
        {"trade_date": date(2024, 2, 29), "decision": "ADJUST", "reasons": ("单只股票权重超过 30%，超出的部分留作现金",)},
        {"trade_date": date(2024, 1, 31), "decision": "ADJUST", "reasons": ("单只股票权重超过 30%，超出的部分留作现金",)},
        {"trade_date": date(2024, 3, 29), "decision": "REJECT", "reasons": ("账户回撤达到 20% 停止线，已清仓，不再开仓",)},
    ]
    report = assess_backtest_validity(nav, start_date=date(2024, 1, 2), end_date=date(2024, 1, 8), risk_interventions=interventions)
    issues = {issue.code: issue for issue in report.issues}
    assert issues["RISK_ADJUSTED_TARGETS"].message == (
        "风控调整了 2 个调仓日的目标持仓，按限制减少了仓位：单只股票权重超过 30%，超出的部分留作现金（2 次，第一次 2024-01-31）。")
    assert issues["RISK_REJECTED_TARGETS"].message == (
        "风控拒绝了 1 个调仓日的目标持仓，这些天没有调仓：账户回撤达到 20% 停止线，已清仓，不再开仓（1 次，第一次 2024-03-29）。")
    assert {issue.severity.value for issue in issues.values() if issue.code.startswith("RISK_")} == {"WARNING"}
    quiet = assess_backtest_validity(nav, start_date=date(2024, 1, 2), end_date=date(2024, 1, 8))
    assert not [issue for issue in quiet.issues if issue.code.startswith("RISK_")]
