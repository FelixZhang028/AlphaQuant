"""Beginner templates and a safe visual strategy builder."""

from __future__ import annotations

from quant_platform.web.theme import inject_global_css

inject_global_css()


import re
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import streamlit as st

from quant_platform.application.backtest_service import BacktestService
from quant_platform.application.strategy_studio_service import (
    StrategyPackage,
    StrategyStudioService,
)
from quant_platform.strategies.rule_schema import (
    INDICATOR_LABELS,
    OPERATOR_LABELS,
    IndicatorSpec,
    RankingSpec,
    RuleSpec,
    RuleStrategyDefinition,
)
from quant_platform.strategies.templates import STYLE_LABELS, beginner_templates

_FREQUENCY_LABELS = {"daily": "每日", "weekly": "每周", "monthly": "每月"}
_FREQUENCY_VALUES = {label: value for value, label in _FREQUENCY_LABELS.items()}
_DIRECTION_LABELS = {"descending": "从高到低", "ascending": "从低到高"}
_INDICATOR_VALUES = {label: value for value, label in INDICATOR_LABELS.items()}
_OPERATOR_VALUES = {label: value for value, label in OPERATOR_LABELS.items()}


def _indicator_widgets(prefix: str, *, include_close: bool = True) -> IndicatorSpec:
    names = list(INDICATOR_LABELS)
    if not include_close:
        names.remove("close")
    labels = [INDICATOR_LABELS[name] for name in names]
    label = st.selectbox("指标", labels, key=f"{prefix}_indicator")
    name = _INDICATOR_VALUES[label]
    window = None
    if name != "close":
        window = int(
            st.number_input(
                "周期（交易日）",
                min_value=1,
                max_value=500,
                value=20,
                step=1,
                key=f"{prefix}_window",
            )
        )
    return IndicatorSpec(name, window)


def _safe_id(name: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_")
    return clean[:60] or "visual_strategy"


def _template_advanced_settings(
    definition: RuleStrategyDefinition, *, prefix: str
) -> RuleStrategyDefinition:
    """Expose template-specific periods and thresholds behind a collapsed panel."""

    tuned_rules: list[RuleSpec] = []
    with st.expander("高级设置（可选）", expanded=False):
        st.caption("周期越短反应越快，但更容易频繁交易；周期越长通常更平稳，但反应更慢。")
        for index, rule in enumerate(definition.entry_rules):
            st.markdown(f"**条件{index + 1}：{rule.describe()}**")
            left = rule.left
            if left.window is not None:
                left = replace(
                    left,
                    window=int(
                        st.number_input(
                            f"{left.describe()}的观察周期",
                            min_value=1,
                            max_value=500,
                            value=left.window,
                            step=1,
                            key=f"{prefix}_rule_{index}_left_window",
                        )
                    ),
                )
            right = rule.right
            value = rule.value
            if right is not None and right.window is not None:
                right = replace(
                    right,
                    window=int(
                        st.number_input(
                            f"{right.describe()}的观察周期",
                            min_value=1,
                            max_value=500,
                            value=right.window,
                            step=1,
                            key=f"{prefix}_rule_{index}_right_window",
                        )
                    ),
                )
            elif value is not None:
                value = float(
                    st.number_input(
                        f"条件{index + 1}的比较值",
                        value=float(value),
                        format="%.4f",
                        key=f"{prefix}_rule_{index}_value",
                        help="收益率使用小数，例如5%填写0.05；成交额单位为元。",
                    )
                )
            tuned_rules.append(replace(rule, left=left, right=right, value=value))

        ranking = definition.ranking.indicator
        if ranking.window is not None:
            ranking = replace(
                ranking,
                window=int(
                    st.number_input(
                        f"排序指标“{ranking.describe()}”的观察周期",
                        min_value=1,
                        max_value=500,
                        value=ranking.window,
                        step=1,
                        key=f"{prefix}_ranking_window",
                    )
                ),
            )
    return replace(
        definition,
        entry_rules=tuple(tuned_rules),
        ranking=replace(definition.ranking, indicator=ranking),
    )


def _show_package(package: StrategyPackage) -> None:
    description = package.definition.describe(
        top_n=package.top_n, rebalance=package.rebalance
    )
    st.markdown(f"**策略说明：** {description}")
    st.caption(
        f"最低历史数据要求：{package.definition.minimum_history_days}个交易日；"
        "停牌、ST、未上市和未知状态由平台安全规则过滤。"
    )


def _remember_result(run: Any, state_key: str) -> None:
    """Persist the result across the rerun triggered by the navigation button."""

    st.session_state[state_key] = {
        "run_id": str(run.result.run_id),
        "summary": dict(run.result.summary),
    }


def _show_result(state_key: str) -> None:
    remembered = st.session_state.get(state_key)
    if not isinstance(remembered, dict):
        return
    run_id = str(remembered.get("run_id", ""))
    summary = remembered.get("summary", {})
    if not run_id or not isinstance(summary, dict):
        return
    st.success("可信度检查通过，回测已经保存。")
    columns = st.columns(4)
    columns[0].metric("累计收益", f"{float(summary.get('cumulative_return', 0)):.2%}")
    columns[1].metric("最大回撤", f"{float(summary.get('max_drawdown', 0)):.2%}")
    columns[2].metric("夏普比率", f"{float(summary.get('sharpe', 0)):.2f}")
    columns[3].metric("成交笔数", str(summary.get("fills", 0)))
    if st.button("打开完整回测结果", key=f"open_{state_key}_{run_id}"):
        st.session_state["selected_run"] = run_id
        st.switch_page("home.py")


st.title("零代码策略工作台")
st.caption("选择模板，或者像搭积木一样描述条件。平台只执行白名单规则，不运行用户代码。")

config_path = "configs/app.yaml"  # 正式版固定配置路径，不再提供侧栏修改入口
try:
    backtests = BacktestService(config_path)
    studio = StrategyStudioService(backtests)
    default_request = backtests.default_request()
except Exception as exc:
    st.error(f"无法加载策略工作台：{exc}")
    st.stop()

template_tab, builder_tab, saved_tab = st.tabs(
    ["模板快速回测", "积木创建策略", "已保存策略"]
)

with template_tab:
    templates = beginner_templates()
    template_by_name = {template.name: template for template in templates}
    template_name = st.selectbox("选择一种容易理解的策略", list(template_by_name))
    template = template_by_name[template_name]
    style_label = st.radio(
        "选择风格",
        list(STYLE_LABELS.values()),
        index=1,
        horizontal=True,
    )
    style = {label: value for value, label in STYLE_LABELS.items()}[style_label]
    preset = template.presets[style]
    st.info(template.summary)
    left, right = st.columns(2)
    left.markdown(f"**适合：** {template.suitable_market}")
    right.markdown(f"**主要风险：** {template.main_risk}")

    with st.form("beginner_template_form"):
        basic_left, basic_middle, basic_right = st.columns(3)
        start_date = basic_left.date_input("回测开始日期", default_request.start_date)
        end_date = basic_left.date_input("回测结束日期", default_request.end_date)
        initial_cash = basic_middle.number_input(
            "初始资金（元）", min_value=10_000.0, value=default_request.initial_cash, step=10_000.0
        )
        top_n = int(
            basic_middle.number_input(
                "持股数量", min_value=1, max_value=50, value=preset.top_n, step=1
            )
        )
        frequency_label = basic_right.selectbox(
            "调仓频率",
            list(_FREQUENCY_VALUES),
            index=list(_FREQUENCY_VALUES).index(_FREQUENCY_LABELS[preset.rebalance]),
        )
        st.caption("股票范围使用“股票池管理”中的当前股票池；平台始终排除不可安全交易的数据。")
        tuned_definition = _template_advanced_settings(
            preset.definition, prefix=f"{template.template_id}_{style}"
        )
        run_template = st.form_submit_button("开始模板回测", type="primary")

    package = replace(
        studio.template_package(template.template_id, style),
        definition=tuned_definition,
        top_n=top_n,
        rebalance=_FREQUENCY_VALUES[frequency_label],
    )
    _show_package(package)
    for warning in studio.preflight(package):
        st.warning(warning)
    if run_template:
        request = replace(
            default_request,
            start_date=start_date,
            end_date=end_date,
            initial_cash=float(initial_cash),
        )
        try:
            with st.spinner("正在进行数据检查和回测……"):
                completed = studio.run(package, base_request=request)
            _remember_result(completed, "template_backtest_result")
        except Exception as exc:
            st.exception(exc)
    _show_result("template_backtest_result")

with builder_tab:
    st.subheader("第一步：填写策略名称和条件")
    with st.form("visual_strategy_builder"):
        strategy_name = st.text_input("策略名称", "我的零代码策略", max_chars=80)
        logic_label = st.radio(
            "条件组合",
            ["全部满足", "任意满足"],
            horizontal=True,
            help="新手建议使用“全部满足”。",
        )
        condition_count = int(
            st.number_input("条件数量", min_value=1, max_value=6, value=2, step=1)
        )
        rules: list[RuleSpec] = []
        for index in range(condition_count):
            st.markdown(f"**条件 {index + 1}**")
            left_column, operator_column, mode_column, right_column = st.columns(
                [2, 1.2, 1.3, 2]
            )
            with left_column:
                left_indicator = _indicator_widgets(f"rule_{index}_left")
            with operator_column:
                operator_label = st.selectbox(
                    "判断",
                    list(_OPERATOR_VALUES),
                    key=f"rule_{index}_operator",
                )
            with mode_column:
                right_mode = st.selectbox(
                    "比较对象",
                    ["固定数值", "另一个指标"],
                    key=f"rule_{index}_mode",
                )
            if right_mode == "固定数值":
                with right_column:
                    fixed_value = float(
                        st.number_input(
                            "比较值",
                            value=0.0,
                            format="%.4f",
                            key=f"rule_{index}_value",
                            help="收益率请填小数，例如5%填0.05；成交额单位为元。",
                        )
                    )
                rule = RuleSpec(
                    left_indicator,
                    _OPERATOR_VALUES[operator_label],
                    value=fixed_value,
                )
            else:
                with right_column:
                    right_indicator = _indicator_widgets(f"rule_{index}_right")
                rule = RuleSpec(
                    left_indicator,
                    _OPERATOR_VALUES[operator_label],
                    right=right_indicator,
                )
            rules.append(rule)

        st.subheader("第二步：设置排序和持仓")
        rank_left, rank_middle, rank_right = st.columns(3)
        with rank_left:
            ranking_indicator = _indicator_widgets("ranking", include_close=False)
        with rank_middle:
            direction_label = st.selectbox("排序方向", list(_DIRECTION_LABELS.values()))
            builder_top_n = int(
                st.number_input("持股数量", min_value=1, max_value=50, value=5, step=1)
            )
        with rank_right:
            builder_frequency_label = st.selectbox(
                "调仓频率", list(_FREQUENCY_VALUES), index=1, key="builder_frequency"
            )
        validate_builder = st.form_submit_button("生成并检查策略", type="primary")

    if validate_builder:
        try:
            definition = RuleStrategyDefinition(
                strategy_id=_safe_id(strategy_name),
                name=strategy_name.strip(),
                description="由零代码积木编辑器创建",
                entry_logic="all" if logic_label == "全部满足" else "any",
                entry_rules=tuple(rules),
                ranking=RankingSpec(
                    ranking_indicator,
                    {label: value for value, label in _DIRECTION_LABELS.items()}[
                        direction_label
                    ],
                ),
            )
            definition.validate()
            draft = StrategyPackage(
                package_id="draft",
                name=definition.name,
                definition=definition,
                top_n=builder_top_n,
                rebalance=_FREQUENCY_VALUES[builder_frequency_label],
                source="visual_builder",
                created_at=datetime.now(UTC),
            )
            draft.validate()
            st.session_state["visual_strategy_draft"] = draft.to_dict()
        except Exception as exc:
            st.error(f"策略检查未通过：{exc}")

    draft_value = st.session_state.get("visual_strategy_draft")
    if draft_value:
        draft = StrategyPackage.from_mapping(draft_value)
        st.success("策略结构合法，可以保存或回测。")
        _show_package(draft)
        warnings = studio.preflight(draft)
        for warning in warnings:
            st.warning(warning)
        save_column, run_column = st.columns(2)
        if save_column.button("保存策略", type="secondary"):
            saved = studio.store.save(
                draft.definition,
                top_n=draft.top_n,
                rebalance=draft.rebalance,
            )
            st.success(f"已保存：{saved.name}（{saved.package_id}）")
        if run_column.button("使用该策略回测", type="primary"):
            try:
                with st.spinner("正在进行规则检查和回测……"):
                    completed = studio.run(draft)
                _remember_result(completed, "builder_backtest_result")
            except Exception as exc:
                st.exception(exc)
        _show_result("builder_backtest_result")

with saved_tab:
    packages = studio.store.list()
    if not packages:
        st.info("还没有保存的积木策略。请先在“积木创建策略”中生成并保存。")
    else:
        package_by_id = {package.package_id: package for package in packages}
        package_id = st.selectbox(
            "选择策略",
            list(package_by_id),
            format_func=lambda value: f"{package_by_id[value].name}｜{value}",
        )
        selected = package_by_id[package_id]
        _show_package(selected)
        copy_column, run_saved_column = st.columns(2)
        if copy_column.button("复制为新策略"):
            copied = studio.store.copy(selected.package_id)
            st.success(f"已创建副本：{copied.name}")
        if run_saved_column.button("回测已保存策略", type="primary"):
            try:
                with st.spinner("正在回测……"):
                    completed = studio.run(selected)
                _remember_result(completed, "saved_backtest_result")
            except Exception as exc:
                st.exception(exc)
        _show_result("saved_backtest_result")

st.divider()
st.caption(
    "安全边界：普通模式最多6个条件；底层协议最多10个条件；不支持任意Python代码；"
    "所有指标只读取调仓日及以前的数据。"
)
