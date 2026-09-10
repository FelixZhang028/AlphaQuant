"""因子研究室（反馈第 9 / 10 / 11 条）。

四个标签页：
- 因子库：浏览全部因子（内置 + 自定义）的说明、公式、所需字段、方向与版本；
- 因子评估：覆盖率、IC / Rank IC、五分位收益、多空收益、换手率、
  因子衰减（前后半段 IC 对比，即样本外稳定性）；
- 因子组合：去极值 / 标准化 / 缺失值处理，等权 / IC 加权 / 自定义权重合成，
  相关性分析与高相关剔除，并一键生成可回测的「因子合成策略」；
- 自定义因子：用字段 / 算子 / 窗口定义量价因子，定义后可参与评估与组合。
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from quant_platform.application.factor_research_service import research_combination
from quant_platform.data.repositories.parquet_repository import (
    ParquetMarketDataRepository,
)
from quant_platform.factors.base import FactorDefinition
from quant_platform.factors.custom import (
    FIELDS,
    OPERATORS,
    build_custom_factor,
    load_custom_factors,
    save_custom_factors,
)
from quant_platform.factors.evaluation import FactorEvaluator, FactorReport
from quant_platform.factors.registry import default_registry, reload_default_registry
from quant_platform.web.service_cache import (
    data_fingerprint,
    get_coverage_bars,
    get_data_repository,
    service_or_stop,
)
from quant_platform.web.theme import inject_global_css

inject_global_css()

_DIRECTION_LABELS = {1: "正向（值越大越看好）", -1: "反向（值越小越看好）"}
_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _evaluate(
    factor: FactorDefinition,
    repository: ParquetMarketDataRepository,
    start: date,
    end: date,
    horizon: int,
    n_groups: int,
) -> FactorReport:
    return FactorEvaluator(repository).evaluate(
        factor, start, end, horizon=horizon, n_groups=n_groups
    )


def _render_report(report: FactorReport) -> None:
    """渲染单因子（或复合因子）评估报告。"""

    metric_cols = st.columns(4)
    metric_cols[0].metric("IC 均值", f"{report.ic_mean:.4f}")
    metric_cols[1].metric("Rank IC 均值", f"{report.rank_ic_mean:.4f}")
    metric_cols[2].metric("Rank IC IR", f"{report.rank_ic_ir:.2f}")
    metric_cols[3].metric("同日多空收益差均值", f"{report.long_short_mean:.2%}")

    stability_cols = st.columns(3)
    stability_cols[0].metric("前半段 Rank IC", f"{report.first_half_ic:.4f}")
    stability_cols[1].metric("后半段 Rank IC", f"{report.second_half_ic:.4f}")
    stability_cols[2].metric("Top 组成员更替率（日频）", f"{report.turnover_mean:.2%}")
    st.caption(
        f"t 日收盘后生成信号，t+1 日收盘买入，t+{report.horizon + 1} 日收盘卖出，"
        f"持有 {report.horizon} 个交易日。多空为同日最高组减最低组收益的均值，未扣交易成本；"
        "成员更替率为新增成员占当日 Top 组人数的比例，不是持仓权重换手率。"
    )
    if not pd.isna(report.first_half_ic) and not pd.isna(report.second_half_ic):
        if report.first_half_ic > 0 and report.second_half_ic < report.first_half_ic / 2:
            st.warning(
                "因子衰减提示：后半段 Rank IC 明显弱于前半段，"
                "因子有效性可能正在衰减，样本外使用需谨慎。"
            )

    for note in report.notes:
        st.info(note)

    if not report.group_mean_returns.empty:
        st.markdown(
            f"**{report.n_groups} 分组平均未来收益**（第 {report.n_groups} 组为因子值最高组）"
        )
        group_frame = report.group_mean_returns.rename("平均未来收益").to_frame()
        group_frame.index = pd.Index([f"第 {i} 组" for i in group_frame.index])
        st.bar_chart(group_frame)
    if not report.daily_ic.empty:
        st.markdown("**Rank IC 走势**")
        st.line_chart(report.daily_ic.set_index("date")[["rank_ic"]])


st.title("因子实验室")
st.caption(
    "统一的因子定义、计算与评估：因子值只使用当日及之前的数据（防未来函数），"
    "持有 N 个交易日：t+1 日收盘买入，t+N+1 日收盘卖出。"
)

flash = st.session_state.pop("custom_factor_flash", None)
if flash:
    st.success(flash)

repository = service_or_stop(get_data_repository, "无法加载数据仓库")

registry = default_registry()
custom_factors = load_custom_factors()

# 以英文名唯一索引全部因子（内置 + 自定义），供评估 / 组合选择。
factors = {item.name: item for item in registry.list()}
factor_names = list(factors)

coverage_bars = get_coverage_bars("configs/app.yaml", data_fingerprint(repository))
if coverage_bars.empty:
    st.warning("本地还没有行情数据。请先到「数据管理」更新股票池行情。")

library_tab, evaluate_tab, combine_tab, custom_tab = st.tabs(
    ["因子库", "因子评估", "因子组合", "自定义因子"]
)

# ------------------------------------------------------------ 因子库 ----
with library_tab:
    st.subheader(f"全部因子（共 {len(registry)} 个）")
    rows = [
        {
            "因子名": item.name,
            "中文名": item.display_name,
            "类别": item.category,
            "说明": item.description,
            "计算公式": item.formula,
            "所需字段": ", ".join(item.required_fields),
            "最小历史": f"{item.min_history} 日",
            "方向": _DIRECTION_LABELS[item.direction],
            "版本": item.version,
        }
        for item in registry.list()
    ]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

# ------------------------------------------------------------ 因子评估 ----
with evaluate_tab:
    sel_col1, sel_col2, sel_col3 = st.columns(3)
    with sel_col1:
        factor_name = st.selectbox(
            "选择因子",
            factor_names,
            format_func=lambda name: factors[name].display_name,
            key="factor_eval_name",
        )
    with sel_col2:
        horizon = st.selectbox("持有期（未来收益天数）", [1, 5, 10, 20], index=1)
    with sel_col3:
        n_groups = st.selectbox("分组数", [5, 10], index=0)

    today = date.today()
    date_col1, date_col2 = st.columns(2)
    with date_col1:
        start = st.date_input("评估开始", today - timedelta(days=365), key="factor_start")
    with date_col2:
        end = st.date_input("评估结束", today, key="factor_end")

    if st.button("开始评估", type="primary", key="factor_eval_run"):
        factor = factors[factor_name]
        report: FactorReport | None = None
        with st.spinner(f"正在评估因子「{factor.display_name}」……"):
            try:
                report = _evaluate(factor, repository, start, end, horizon, n_groups)
            except Exception as exc:  # noqa: BLE001 - 数据不足等场景给出可读提示
                st.error(f"评估失败：{exc}")
        if report is not None:
            coverage = len(report.daily_ic)
            st.caption(
                f"覆盖率：{coverage} 个有效交易日截面 ｜ 持有期 {horizon} 日 ｜ {n_groups} 分组"
            )
            _render_report(report)

# ------------------------------------------------------------ 因子组合 ----
with combine_tab:
    st.subheader("多因子合成")
    st.caption("先用训练期确定规则，再用独立测试期比较选股能力；实际收益与回撤请到回测页验证。")
    st.markdown("### 1 · 选择因子")
    selected = st.multiselect(
        "选择至少两个因子",
        factor_names,
        default=factor_names[:2],
        format_func=lambda name: factors[name].display_name,
        key="factor_combine_names",
    )
    st.markdown("### 2 · 设置组合")
    weight_mode = st.selectbox(
        "组合方式", ["等权", "手动权重", "自动权重（高级）"], key="factor_weight_mode_v2"
    )
    custom_weights = {}
    if weight_mode == "手动权重":
        st.caption("数字表示相对份额，系统会归一化为百分比；0 表示不参与打分。")
        for name in selected:
            custom_weights[name] = st.number_input(
                f"{factors[name].display_name} 权重",
                min_value=0.0,
                value=1.0,
                key=f"factor_w_{name}",
            )
    with st.expander("高级设置：清洗与自动权重说明"):
        do_winsorize = st.checkbox("按日去极值（MAD）", value=True, key="factor_winsorize")
        fill_method = st.selectbox("缺失值处理", ["剔除缺失", "中位数填充"], key="factor_fill")
        st.caption("各因子统一方向后按日标准化。所有对比方案使用相同清洗设置和共同样本。")
        st.caption("自动权重只使用训练期 Rank IC：正值参与分配，负值或无效值权重为零。")
        st.caption("相关性仅作提示，不会自动删除因子；删除或修改因子后需重新验证。")
    st.markdown("### 3 · 划分训练与测试日期")
    train_col, test_col = st.columns(2)
    with train_col:
        train_start = st.date_input(
            "训练开始", today - timedelta(days=730), key="combo_train_start"
        )
        train_end = st.date_input("训练结束", today - timedelta(days=366), key="combo_train_end")
    with test_col:
        test_start = st.date_input("测试开始", today - timedelta(days=365), key="combo_test_start")
        test_end = st.date_input("测试结束", today, key="combo_test_end")
    periods, groups = st.columns(2)
    combo_horizon = periods.selectbox(
        "组合持有期（交易日）", [1, 5, 10, 20], index=1, key="combo_horizon"
    )
    combo_groups = groups.selectbox("组合分组数", [5, 10], key="combo_groups")
    st.caption("训练期收益不读取训练结束日之后的价格；测试期也只使用测试结束日前已完成的收益。")
    st.caption("反复查看测试结果并调参会让测试集失去独立性，正式使用前还应保留新的未见数据。")
    mode = {"等权": "equal", "手动权重": "manual", "自动权重（高级）": "ic"}[weight_mode]
    config = dict(
        train_start=train_start,
        train_end=train_end,
        test_start=test_start,
        test_end=test_end,
        mode=mode,
        custom_weights=custom_weights,
        clip=do_winsorize,
        missing="drop" if fill_method == "剔除缺失" else "median",
        horizon=combo_horizon,
        n_groups=combo_groups,
    )
    fingerprint = json.dumps(
        {
            "config": config,
            "factors": [(name, factors[name].version) for name in selected],
            "user": st.session_state.get("aq_authenticated_user"),
        },
        default=str,
        sort_keys=True,
    )
    if st.button("开始验证", type="primary", key="factor_combine_run"):
        st.session_state.pop("factor_research_result", None)
        st.session_state.pop("factor_composite_spec", None)
        try:
            with st.spinner("正在训练并验证组合……"):
                result = research_combination(
                    repository, tuple(factors[name] for name in selected), **config
                )
            st.session_state["factor_research_result"] = (fingerprint, result)
        except (ValueError, KeyError, TypeError) as exc:
            st.error(f"组合验证失败：{exc}")
    saved = st.session_state.get("factor_research_result")
    if saved and saved[0] != fingerprint:
        st.info("设置已变化，请重新验证；旧结果不会带入回测。")
    if saved and saved[0] == fingerprint:
        result = saved[1]
        st.markdown("### 4 · 查看测试期结果")
        st.markdown("**实际权重与公式**")
        st.dataframe(
            pd.DataFrame(
                [
                    {"因子": factors[name].display_name, "权重": f"{weight:.1%}"}
                    for name, weight in result.weights.items()
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        formula = " + ".join(
            f"{weight:.4f} × 标准分({factors[name].display_name}，方向{factors[name].direction:+d})"
            for name, weight in result.weights.items()
            if weight > 0
        )
        st.code("综合得分 = " + formula, language=None)
        st.caption("标准分使用统一方向、清洗后的当日横截面计算。")
        with st.expander("训练期因子相关性"):
            st.dataframe(result.correlation.round(3), width="stretch")
            if not result.correlation.empty:
                corr_values = result.correlation.abs().copy()
                for name in corr_values.index:
                    corr_values.loc[name, name] = 0
                if corr_values.ge(0.7).any().any():
                    st.info("部分因子相关性达到 0.7，可能包含重复信息，可检查后重新选择。")
        st.dataframe(result.comparison, hide_index=True, width="stretch")
        st.caption(
            "收益差与更替率以小数表示（0.01 = 1%）；不等同于扣费后可交易收益。"
            "等权模式下两组合一致。"
        )
        detail = st.selectbox("查看方案详情", list(result.reports), key="combo_report_detail")
        _render_report(result.reports[detail])
        export = {
            "version": 1,
            "config": json.loads(fingerprint),
            "factors": result.spec,
            "comparison": json.loads(result.comparison.to_json(orient="records")),
            "reports": {
                name: {
                    "daily_ic": json.loads(
                        report.daily_ic.to_json(orient="records", date_format="iso")
                    ),
                    "group_returns": json.loads(
                        report.group_returns.to_json(orient="records", date_format="iso")
                    ),
                    "notes": report.notes,
                }
                for name, report in result.reports.items()
            },
        }
        st.download_button(
            "下载组合与验证记录",
            json.dumps(export, ensure_ascii=False, indent=2),
            file_name="factor_research.json",
            mime="application/json",
            key="combo_download",
        )
        st.caption("带入回测会保留已验证的权重与清洗规则；请在回测页确认交易日期、股票池与成本。")
        if st.button("保存组合并去回测", key="factor_to_strategy"):
            st.session_state["factor_composite_payload"] = result.spec
            st.session_state["backtest_workspace_mode"] = "单次回测"
            st.switch_page("home.py")

# ------------------------------------------------------------ 自定义因子 ----
with custom_tab:
    st.subheader("自定义因子")
    st.caption("用字段、算子和窗口定义一个量价因子，定义后可到「因子评估」和「因子组合」中使用。")

    with st.form("custom_factor_form"):
        col1, col2 = st.columns(2)
        with col1:
            name_input = st.text_input(
                "因子标识（英文，唯一）", placeholder="my_factor", key="cf_name"
            )
            field = st.selectbox(
                "计算字段", list(FIELDS), format_func=lambda key: FIELDS[key], key="cf_field"
            )
        with col2:
            display_input = st.text_input(
                "显示名（中文，可选）", placeholder="我的因子", key="cf_display"
            )
            operator = st.selectbox(
                "算子",
                list(OPERATORS),
                format_func=lambda key: str(OPERATORS[key]["label"]),
                key="cf_operator",
            )
        operator_meta = OPERATORS[operator]
        win1, win2 = st.columns(2)
        with win1:
            window = int(st.number_input("窗口 N", min_value=1, value=20, step=1, key="cf_window"))
        with win2:
            if operator_meta["window2"]:
                window2 = int(
                    st.number_input(
                        "第二窗口 N2（长窗口）", min_value=1, value=60, step=1, key="cf_window2"
                    )
                )
            else:
                window2 = None
        direction = st.radio(
            "因子方向",
            [1, -1],
            index=0 if int(operator_meta["direction"]) == 1 else 1,
            format_func=lambda value: _DIRECTION_LABELS[value],
            horizontal=True,
            key="cf_direction",
        )
        description = st.text_input("说明（可选）", key="cf_description")
        submitted = st.form_submit_button("添加因子", type="primary")

    if submitted:
        errors: list[str] = []
        clean_name = (name_input or "").strip()
        if not clean_name:
            errors.append("请填写因子标识。")
        elif not _NAME_PATTERN.fullmatch(clean_name):
            errors.append("因子标识只能包含字母、数字、下划线，且以字母或下划线开头。")
        elif clean_name in factors:
            errors.append(f"因子标识 {clean_name!r} 已被内置或自定义因子占用。")
        if operator_meta["window2"] and window2 is not None and window2 <= window:
            errors.append("第二窗口 N2 应大于窗口 N（短均线在前）。")

        if errors:
            for message in errors:
                st.error(message)
        else:
            try:
                factor = build_custom_factor(
                    clean_name,
                    display_name=(display_input or "").strip(),
                    description=(description or "").strip(),
                    field=field,
                    operator=operator,
                    window=window,
                    window2=window2,
                    direction=int(direction),
                )
            except Exception as exc:  # noqa: BLE001
                st.error(f"无法创建因子：{exc}")
            else:
                updated = [item for item in custom_factors if item.name != factor.name]
                updated.append(factor)
                save_custom_factors(updated)
                reload_default_registry()
                st.session_state["custom_factor_flash"] = (
                    f"已添加自定义因子：{factor.display_name}（{factor.name}）"
                )
                st.rerun()

    st.divider()
    st.markdown("**已定义的自定义因子**")
    if not custom_factors:
        st.info("还没有自定义因子。定义后可到「因子评估」和「因子组合」中使用。")
    else:
        for factor in custom_factors:
            info_col, action_col = st.columns([5, 1])
            with info_col:
                st.markdown(f"**{factor.display_name}**（{factor.name}）")
                detail = (
                    f"{FIELDS.get(factor.field, factor.field)} ｜ "
                    f"{OPERATORS.get(factor.operator, {}).get('label', factor.operator)} ｜ "
                    f"窗口 {factor.window}"
                )
                if factor.window2 is not None:
                    detail += f" / {factor.window2}"
                detail += f" ｜ {_DIRECTION_LABELS[factor.direction]}"
                st.caption(detail)
            with action_col:
                if st.button("删除", key=f"del_custom_{factor.name}"):
                    remaining = [item for item in custom_factors if item.name != factor.name]
                    save_custom_factors(remaining)
                    reload_default_registry()
                    st.session_state["custom_factor_flash"] = (
                        f"已删除自定义因子：{factor.display_name}（{factor.name}）"
                    )
                    st.rerun()
