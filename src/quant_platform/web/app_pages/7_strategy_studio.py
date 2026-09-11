"""Beginner templates and a safe visual strategy builder."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, replace
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
from quant_platform.web.embedded_page import is_embedded
from quant_platform.web.theme import inject_global_css

inject_global_css()

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
        minimum, maximum = IndicatorSpec(name).window_limits
        key = f"{prefix}_window"
        if key in st.session_state:
            st.session_state[key] = max(minimum, min(maximum, int(st.session_state[key])))
        window = int(
            st.number_input(
                "周期（交易日）",
                min_value=minimum,
                max_value=maximum,
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
                            min_value=left.window_limits[0],
                            max_value=left.window_limits[1],
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
                            min_value=right.window_limits[0],
                            max_value=right.window_limits[1],
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
                        min_value=ranking.window_limits[0],
                        max_value=ranking.window_limits[1],
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
    description = package.definition.describe(top_n=package.top_n, rebalance=package.rebalance)
    st.markdown(f"**策略说明：** {description}")
    st.caption(
        f"最低历史数据要求：{package.definition.minimum_history_days}个交易日；"
        "停牌、ST、未上市和未知状态由平台安全规则过滤。"
    )


def _remember_result(run: Any, state_key: str, signature: str) -> None:
    """Persist the result across the rerun triggered by the navigation button."""

    st.session_state[state_key] = {
        "signature": signature,
        "run_id": str(run.result.run_id),
        "summary": dict(run.result.summary),
    }


def _show_result(state_key: str, signature: str) -> None:
    remembered = st.session_state.get(state_key)
    if not isinstance(remembered, dict):
        return
    if remembered.get("signature") != signature:
        st.info("策略或回测设置已变化，请重新回测；旧结果可在研究记录中查看。")
        return
    run_id = str(remembered.get("run_id", ""))
    summary = remembered.get("summary", {})
    if not run_id or not isinstance(summary, dict):
        return
    st.success(f"当前配置的回测已保存，记录编号：{run_id}")
    columns = st.columns(4)
    columns[0].metric("累计收益", f"{float(summary.get('cumulative_return', 0)):.2%}")
    columns[1].metric("最大回撤", f"{float(summary.get('max_drawdown', 0)):.2%}")
    columns[2].metric("夏普比率", f"{float(summary.get('sharpe', 0)):.2f}")
    columns[3].metric("成交笔数", str(summary.get("fills", 0)))
    if st.button("打开完整回测结果", key=f"open_{state_key}_{run_id}"):
        st.session_state["selected_run"] = run_id
        st.session_state["backtest_workspace_mode"] = "单次回测"
        st.switch_page("home.py")


def _definition_signature(value: dict) -> str:
    return json.dumps(
        {k: value[k] for k in ("definition", "top_n", "rebalance")},
        ensure_ascii=False,
        sort_keys=True,
    )


def _signature(package: StrategyPackage, request: Any) -> str:
    return json.dumps(
        {
            "package": _definition_signature(package.to_dict()),
            "id": package.package_id,
            "request": asdict(request),
        },
        default=str,
        sort_keys=True,
    )


def _load_editor(package: StrategyPackage) -> None:
    # Called before widgets are instantiated; never mutate existing widget keys mid-render.
    for key in list(st.session_state):
        if key.startswith(("rule_", "ranking_", "builder_")) or key == "visual_strategy_draft":
            del st.session_state[key]
    definition = package.definition
    st.session_state.update(
        {
            "studio_edit_origin": package.to_dict(),
            "builder_name": definition.name,
            "builder_logic": "全部满足" if definition.entry_logic == "all" else "任意满足",
            "builder_count": len(definition.entry_rules),
            "builder_top_n": package.top_n,
            "builder_frequency": _FREQUENCY_LABELS[package.rebalance],
            "builder_direction": _DIRECTION_LABELS[definition.ranking.direction],
        }
    )

    def set_indicator(prefix, indicator):
        st.session_state[f"{prefix}_indicator"] = INDICATOR_LABELS[indicator.name]
        if indicator.window is not None:
            st.session_state[f"{prefix}_window"] = indicator.window

    for index, rule in enumerate(definition.entry_rules):
        prefix = f"rule_{index}"
        set_indicator(f"{prefix}_left", rule.left)
        st.session_state[f"{prefix}_operator"] = OPERATOR_LABELS[rule.operator]
        st.session_state[f"{prefix}_mode"] = "另一个指标" if rule.right else "固定数值"
        if rule.right:
            set_indicator(f"{prefix}_right", rule.right)
        else:
            st.session_state[f"{prefix}_value"] = float(rule.value)
    set_indicator("ranking", definition.ranking.indicator)


if is_embedded("strategy_visual"):
    st.subheader("策略搭建")
else:
    st.title("策略搭建")
st.caption("选择模板，或者像搭积木一样描述条件。平台只执行白名单规则，不运行用户代码。")

config_path = "configs/app.yaml"  # 正式版固定配置路径，不再提供侧栏修改入口
try:
    backtests = BacktestService(config_path)
    studio = StrategyStudioService(backtests)
    default_request = backtests.default_request()
except Exception as exc:
    st.error(f"无法加载策略工作台：{exc}")
    st.stop()

with st.container(border=True):
    st.subheader("回测设置")
    dates_left, dates_right, cash_col = st.columns(3)
    start_date = dates_left.date_input(
        "回测开始日期", default_request.start_date, key="studio_start"
    )
    end_date = dates_right.date_input("回测结束日期", default_request.end_date, key="studio_end")
    initial_cash = cash_col.number_input(
        "初始资金（元）",
        min_value=10000.0,
        value=default_request.initial_cash,
        step=10000.0,
        key="studio_cash",
    )
    st.caption("股票范围使用当前配置的股票池；持股数量和调仓频率使用各策略下方的设置。")
request = replace(
    default_request, start_date=start_date, end_date=end_date, initial_cash=float(initial_cash)
)
if end_date < start_date:
    st.warning("回测结束日期不能早于开始日期，请修正后再运行。")
pending = st.session_state.pop("studio_pending_edit", None)
if pending:
    _load_editor(StrategyPackage.from_mapping(pending))
if st.session_state.get("studio_edit_origin"):
    st.info("已载入保存的策略，请切换到“自定义策略”编辑；保存为新版本会保留原策略。")

template_tab, builder_tab, saved_tab = st.tabs(["策略模板", "自定义策略", "我的策略"])

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

    with st.container():
        basic_middle, basic_right = st.columns(2)
        preset_key = f"template_{template.template_id}_{style}"
        top_n = int(
            basic_middle.number_input(
                "持股数量",
                min_value=1,
                max_value=50,
                value=preset.top_n,
                step=1,
                key=f"{preset_key}_top_n",
            )
        )
        frequency_label = basic_right.selectbox(
            "调仓频率",
            list(_FREQUENCY_VALUES),
            index=list(_FREQUENCY_VALUES).index(_FREQUENCY_LABELS[preset.rebalance]),
            key=f"{preset_key}_frequency",
        )
        tuned_definition = _template_advanced_settings(
            preset.definition, prefix=f"{template.template_id}_{style}"
        )
        run_template = st.button(
            "开始模板回测",
            type="primary",
            key="studio_template_run",
            disabled=end_date < start_date,
        )

    package = replace(
        studio.template_package(template.template_id, style),
        definition=tuned_definition,
        top_n=top_n,
        rebalance=_FREQUENCY_VALUES[frequency_label],
    )
    _show_package(package)
    for warning in studio.preflight(package):
        st.warning(warning)
    template_signature = _signature(package, request)
    if st.button("另存为我的策略", key="studio_save_template"):
        try:
            saved = studio.store.save(
                package.definition,
                top_n=package.top_n,
                rebalance=package.rebalance,
                source=package.source,
            )
            st.success(f"已保存到“我的策略”：{saved.name}")
        except Exception as exc:
            st.error(f"保存失败：{exc}")
    if run_template:
        st.session_state.pop("template_backtest_result", None)
        try:
            with st.spinner("正在进行数据检查和回测……"):
                completed = studio.run(package, base_request=request)
            _remember_result(completed, "template_backtest_result", template_signature)
        except Exception as exc:
            st.exception(exc)
    _show_result("template_backtest_result", template_signature)

with builder_tab:
    st.subheader("第一步：填写策略名称和条件")
    with st.container():
        strategy_name = st.text_input(
            "策略名称", "我的零代码策略", max_chars=80, key="builder_name"
        )
        logic_label = st.radio(
            "条件组合",
            ["全部满足", "任意满足"],
            horizontal=True,
            help="新手建议使用“全部满足”。",
            key="builder_logic",
        )
        condition_count = int(
            st.number_input(
                "条件数量", min_value=1, max_value=6, value=2, step=1, key="builder_count"
            )
        )
        rules: list[RuleSpec] = []
        for index in range(condition_count):
            st.markdown(f"**条件 {index + 1}**")
            left_column, operator_column, mode_column, right_column = st.columns([2, 1.2, 1.3, 2])
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
            ranking_indicator = _indicator_widgets("ranking")
        with rank_middle:
            direction_label = st.selectbox(
                "排序方向", list(_DIRECTION_LABELS.values()), key="builder_direction"
            )
            builder_top_n = int(
                st.number_input(
                    "持股数量", min_value=1, max_value=50, value=5, step=1, key="builder_top_n"
                )
            )
        with rank_right:
            builder_frequency_label = st.selectbox(
                "调仓频率", list(_FREQUENCY_VALUES), index=1, key="builder_frequency"
            )
        validate_builder = st.button("生成并检查策略", type="primary", key="studio_validate")

    origin = st.session_state.get("studio_edit_origin")
    current_definition = RuleStrategyDefinition(
        strategy_id=origin["definition"]["strategy_id"] if origin else _safe_id(strategy_name),
        name=strategy_name.strip(),
        description=origin["definition"]["description"] if origin else "由零代码积木编辑器创建",
        entry_logic="all" if logic_label == "全部满足" else "any",
        entry_rules=tuple(rules),
        ranking=RankingSpec(
            ranking_indicator, {v: k for k, v in _DIRECTION_LABELS.items()}[direction_label]
        ),
    )
    candidate = StrategyPackage(
        package_id="draft",
        name=current_definition.name,
        definition=current_definition,
        top_n=builder_top_n,
        rebalance=_FREQUENCY_VALUES[builder_frequency_label],
        source=f"revision:{origin['package_id']}" if origin else "visual_builder",
        created_at=datetime.now(UTC),
    )
    builder_signature = _signature(candidate, request)
    if validate_builder:
        st.session_state.pop("visual_strategy_draft", None)
        st.session_state.pop("builder_backtest_result", None)
        try:
            candidate.validate()
            st.session_state["visual_strategy_draft"] = candidate.to_dict()
        except Exception as exc:
            st.error(f"策略检查未通过：{exc}")

    draft_value = st.session_state.get("visual_strategy_draft")
    if draft_value and _definition_signature(draft_value) != _definition_signature(
        candidate.to_dict()
    ):
        st.info("条件已修改，请重新点击“生成并检查策略”；旧草稿不可保存或回测。")
        draft_value = None
    if draft_value:
        draft = StrategyPackage.from_mapping(draft_value)
        st.success("策略结构合法，可以保存或回测。")
        _show_package(draft)
        warnings = studio.preflight(draft)
        for warning in warnings:
            st.warning(warning)
        save_column, run_column = st.columns(2)
        if save_column.button(
            "保存为新版本" if origin else "保存策略", type="secondary", key="studio_save"
        ):
            saved = studio.store.save(
                draft.definition,
                top_n=draft.top_n,
                rebalance=draft.rebalance,
                source=draft.source,
            )
            st.success(f"已保存：{saved.name}（{saved.package_id}）")
        if run_column.button("使用该策略回测", type="primary", disabled=end_date < start_date):
            st.session_state.pop("builder_backtest_result", None)
            try:
                with st.spinner("正在进行规则检查和回测……"):
                    completed = studio.run(draft, base_request=request)
                _remember_result(completed, "builder_backtest_result", builder_signature)
            except Exception as exc:
                st.exception(exc)
        _show_result("builder_backtest_result", builder_signature)

with saved_tab:
    packages = studio.store.list()
    if not packages:
        st.info("还没有保存的策略。请先在“自定义策略”中生成并保存，或另存一个策略模板。")
    else:
        package_by_id = {package.package_id: package for package in packages}
        package_id = st.selectbox(
            "选择策略",
            list(package_by_id),
            format_func=lambda value: f"{package_by_id[value].name}｜{value}",
        )
        selected = package_by_id[package_id]
        _show_package(selected)
        if st.button(
            "载入积木编辑", key="studio_load", disabled=len(selected.definition.entry_rules) > 6
        ):
            st.session_state["studio_pending_edit"] = selected.to_dict()
            st.rerun()
        if len(selected.definition.entry_rules) > 6:
            st.caption("此策略超过 6 个条件，当前积木编辑器不能载入；仍可回测或复制。")
        copy_column, run_saved_column = st.columns(2)
        if copy_column.button("复制为新策略"):
            copied = studio.store.copy(selected.package_id)
            st.success(f"已创建副本：{copied.name}")
        if run_saved_column.button(
            "回测已保存策略", type="primary", disabled=end_date < start_date
        ):
            st.session_state.pop("saved_backtest_result", None)
            try:
                with st.spinner("正在回测……"):
                    completed = studio.run(selected, base_request=request)
                _remember_result(completed, "saved_backtest_result", _signature(selected, request))
            except Exception as exc:
                st.exception(exc)
        _show_result("saved_backtest_result", _signature(selected, request))

st.divider()
st.caption(
    "安全边界：普通模式最多6个条件；底层协议最多10个条件；不支持任意Python代码；"
    "所有指标只读取调仓日及以前的数据。"
)
