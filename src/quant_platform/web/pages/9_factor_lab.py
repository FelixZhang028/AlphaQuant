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

import re
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from quant_platform.core.config import load_yaml, require_mapping
from quant_platform.data.repositories.parquet_repository import (
    ParquetMarketDataRepository,
)
from quant_platform.factors.base import FactorDefinition
from quant_platform.factors.combine import (
    CompositeFactor,
    correlation_matrix,
    drop_highly_correlated,
)
from quant_platform.factors.custom import (
    FIELDS,
    OPERATORS,
    build_custom_factor,
    load_custom_factors,
    save_custom_factors,
)
from quant_platform.factors.evaluation import FactorEvaluator, FactorReport
from quant_platform.factors.preprocess import fill_missing, winsorize, zscore
from quant_platform.factors.registry import default_registry, reload_default_registry
from quant_platform.web.theme import inject_global_css

inject_global_css()

_DIRECTION_LABELS = {1: "正向（值越大越看好）", -1: "反向（值越小越看好）"}
_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _repository(config_path: str) -> ParquetMarketDataRepository:
    config = load_yaml(config_path)
    data_section = require_mapping(config, "data")
    return ParquetMarketDataRepository(data_section["repository"])


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
    metric_cols[3].metric("多空收益（每期）", f"{report.long_short_mean:.2%}")

    stability_cols = st.columns(3)
    stability_cols[0].metric("前半段 Rank IC", f"{report.first_half_ic:.4f}")
    stability_cols[1].metric("后半段 Rank IC", f"{report.second_half_ic:.4f}")
    stability_cols[2].metric("Top 组换手率（每期）", f"{report.turnover_mean:.2%}")
    if not pd.isna(report.first_half_ic) and not pd.isna(report.second_half_ic):
        if report.first_half_ic > 0 and report.second_half_ic < report.first_half_ic / 2:
            st.warning(
                "因子衰减提示：后半段 Rank IC 明显弱于前半段，"
                "因子有效性可能正在衰减，样本外使用需谨慎。"
            )

    for note in report.notes:
        st.info(note)

    if not report.group_mean_returns.empty:
        st.markdown("**五分位分组平均未来收益**（第 5 组为因子值最高组）")
        group_frame = report.group_mean_returns.rename("平均未来收益").to_frame()
        group_frame.index = pd.Index([f"第 {i} 组" for i in group_frame.index])
        st.bar_chart(group_frame)
    if not report.daily_ic.empty:
        st.markdown("**Rank IC 走势**")
        st.line_chart(report.daily_ic.set_index("date")[["rank_ic"]])


st.title("因子研究室")
st.caption(
    "统一的因子定义、计算与评估：因子值只使用当日及之前的数据（防未来函数），"
    "IC 与未来收益按 t 日因子对 t+1 至 t+N 收益计算。"
)

flash = st.session_state.pop("custom_factor_flash", None)
if flash:
    st.success(flash)

config_path = "configs/app.yaml"  # 正式版固定配置路径，不再提供侧栏修改入口
try:
    repository = _repository(config_path)
except Exception as exc:  # noqa: BLE001 - 配置损坏时给出可读提示
    st.error(f"无法加载数据仓库：{exc}")
    st.stop()

registry = default_registry()
custom_factors = load_custom_factors()

# 以英文名唯一索引全部因子（内置 + 自定义），供评估 / 组合选择。
factors = {item.name: item for item in registry.list()}
factor_names = list(factors)

coverage_bars = repository.read_table("daily_bars")
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
        with st.spinner(f"正在评估因子「{factor.display_name}」……"):
            try:
                report = _evaluate(factor, repository, start, end, horizon, n_groups)
            except Exception as exc:  # noqa: BLE001 - 数据不足等场景给出可读提示
                st.error(f"评估失败：{exc}")
                st.stop()
        coverage = len(report.daily_ic)
        st.caption(
            f"覆盖率：{coverage} 个有效交易日截面 ｜ 持有期 {horizon} 日 ｜ {n_groups} 分组"
        )
        _render_report(report)

# ------------------------------------------------------------ 因子组合 ----
with combine_tab:
    st.subheader("多因子合成")
    selected = st.multiselect(
        "选择要合成的因子（2 个起）",
        factor_names,
        default=factor_names[:2],
        format_func=lambda name: factors[name].display_name,
        key="factor_combine_names",
    )
    weight_mode = st.radio(
        "权重方式",
        ["等权", "IC 加权（按各自 Rank IC 绝对值）", "自定义权重"],
        horizontal=True,
        key="factor_weight_mode",
    )

    custom_weights: dict[str, float] = {}
    if weight_mode == "自定义权重":
        weight_cols = st.columns(min(4, max(1, len(selected))))
        for index, name in enumerate(selected):
            with weight_cols[index % len(weight_cols)]:
                custom_weights[name] = float(
                    st.number_input(
                        f"{factors[name].display_name} 权重",
                        value=1.0,
                        key=f"factor_w_{name}",
                    )
                )

    with st.expander("清洗选项（去极值 / 标准化 / 缺失值处理）", expanded=False):
        do_winsorize = st.checkbox("MAD 去极值", value=True, key="factor_winsorize")
        do_zscore = st.checkbox("截面标准化（合成前自动执行，此为额外预处理）", value=False)
        fill_method = st.selectbox("缺失值处理", ["剔除缺失", "中位数填充"], key="factor_fill")

    corr_threshold = st.slider("高相关剔除阈值 |ρ|", 0.5, 0.95, 0.7, key="factor_corr_th")

    if st.button("计算并评估合成因子", type="primary", key="factor_combine_run"):
        if len(selected) < 2:
            st.warning("请至少选择两个因子。")
            st.stop()
        components = tuple(factors[name] for name in selected)
        with st.spinner("正在计算成分因子……"):
            frames: dict[str, pd.DataFrame] = {}
            try:
                for factor in components:
                    frame = factor.compute(repository.get_daily_bars())
                    if do_winsorize:
                        frame = winsorize(frame)
                    if do_zscore:
                        frame = zscore(frame)
                    if fill_method == "剔除缺失":
                        frame = fill_missing(frame, method="drop")
                    else:
                        frame = fill_missing(frame, method="median")
                    frames[factor.name] = frame
            except Exception as exc:  # noqa: BLE001
                st.error(f"因子计算失败：{exc}")
                st.stop()

        corr = correlation_matrix(frames)
        if not corr.empty:
            st.markdown("**因子相关性矩阵（按日横截面 Spearman 均值）**")
            st.dataframe(corr.round(3), width="stretch")
            dropped = drop_highly_correlated(corr, threshold=corr_threshold)
            if dropped:
                st.warning(
                    f"以下因子与其他因子相关性超过 {corr_threshold}，已自动剔除："
                    f"{', '.join(dropped)}"
                )
                for name in dropped:
                    frames.pop(name, None)
                components = tuple(item for item in components if item.name in frames)
        if len(components) < 1:
            st.error("高相关剔除后没有剩余因子，请降低剔除阈值或重选因子。")
            st.stop()

        if weight_mode == "等权":
            weights = {item.name: 1.0 for item in components}
        elif weight_mode == "自定义权重":
            weights = {
                item.name: custom_weights.get(item.name, 1.0) for item in components
            }
        else:
            weights = {}
            with st.spinner("正在用 Rank IC 估计权重……"):
                for factor in components:
                    report = _evaluate(factor, repository, start, end, horizon, n_groups)
                    weights[factor.name] = max(abs(report.rank_ic_mean), 1e-4)
            st.caption("IC 加权结果：" + "、".join(
                f"{name}={weight:.4f}" for name, weight in weights.items()
            ))

        composite = CompositeFactor(
            name="composite_custom",
            display_name="自定义合成因子",
            description="因子研究室合成的复合因子",
            formula="weighted sum of z-scored components",
            components=components,
            weights=weights,
        )
        with st.spinner("正在评估合成因子……"):
            try:
                report = _evaluate(composite, repository, start, end, horizon, n_groups)
            except Exception as exc:  # noqa: BLE001
                st.error(f"合成因子评估失败：{exc}")
                st.stop()
        _render_report(report)

        st.session_state["factor_composite_spec"] = [
            {"name": item.name, "weight": float(weights[item.name])} for item in components
        ]

    spec = st.session_state.get("factor_composite_spec")
    if spec:
        st.divider()
        st.subheader("一键转换成选股策略")
        st.caption(
            "把当前合成因子保存为「因子合成策略」参数，随后可在回测页选择 "
            "factor_composite 插件直接运行，或点击下方按钮立即回测。"
        )
        st.code(str(spec), language="json")
        if st.button("保存组合并去回测", key="factor_to_strategy"):
            st.session_state["factor_composite_payload"] = spec
            st.switch_page("home.py")

# ------------------------------------------------------------ 自定义因子 ----
with custom_tab:
    st.subheader("自定义因子")
    st.caption(
        "用字段、算子和窗口定义一个量价因子，定义后可到「因子评估」和「因子组合」中使用。"
    )

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
            window = int(
                st.number_input("窗口 N", min_value=1, value=20, step=1, key="cf_window")
            )
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
