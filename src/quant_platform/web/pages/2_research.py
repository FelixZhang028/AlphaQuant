"""Parameter optimization and persisted backtest comparison."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from quant_platform.application.backtest_service import BacktestService
from quant_platform.application.optimization_service import (
    OBJECTIVES,
    OptimizationRequest,
    OptimizationService,
)
from quant_platform.application.walk_forward_service import (
    WalkForwardRequest,
    WalkForwardService,
)
from quant_platform.strategies.spec import ParameterKind, StrategyParameter
from quant_platform.web.exports import dataframe_to_csv_bytes
from quant_platform.web.localization import localize_frame


def _parse_candidates(parameter: StrategyParameter, raw: str) -> tuple[Any, ...]:
    parts = [part.strip() for part in raw.replace("，", ",").split(",") if part.strip()]
    if not parts:
        raise ValueError(f"{parameter.label} 至少需要一个候选值")
    if parameter.kind == ParameterKind.INTEGER:
        return tuple(int(part) for part in parts)
    if parameter.kind == ParameterKind.NUMBER:
        return tuple(float(part) for part in parts)
    if parameter.kind == ParameterKind.BOOLEAN:
        aliases = {"true": True, "1": True, "是": True, "false": False, "0": False, "否": False}
        try:
            return tuple(aliases[part.lower()] for part in parts)
        except KeyError as exc:
            raise ValueError(f"{parameter.label} 请填写“是,否”（也支持 true,false）") from exc
    return tuple(parts)


def _run_label(record: Any, strategy_names: dict[str, str]) -> str:
    strategy = strategy_names.get(
        record.strategy_plugin,
        record.strategy_plugin or "旧版本策略",
    )
    dates = f"{record.start_date}~{record.end_date}" if record.start_date else "日期未知"
    return f"{strategy} | {dates} | {record.run_id[:8]}"


def _localized_parameters(
    raw: Any,
    strategy_plugin: Any,
    metadata_by_name: dict[str, Any],
) -> str:
    """Translate persisted parameter keys for display without changing stored data."""

    try:
        values = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return str(raw)
    metadata = metadata_by_name.get(str(strategy_plugin))
    labels = (
        {parameter.name: parameter.label for parameter in metadata.parameters}
        if metadata is not None
        else {}
    )
    return json.dumps(
        {labels.get(str(name), str(name)): value for name, value in values.items()},
        ensure_ascii=False,
    )


st.title("策略研究")
st.caption("批量测试策略参数，并把不同回测放在同一张表和净值图中比较。")

config_path = st.sidebar.text_input("策略研究配置", "configs/app.yaml", key="research_config_path")
try:
    service = BacktestService(config_path)
    default_request = service.default_request()
except Exception as exc:
    st.error(f"无法加载策略研究配置：{exc}")
    st.stop()

metadata_by_name = {item.plugin_name: item for item in service.available_strategies()}
strategy_names = {name: item.display_name for name, item in metadata_by_name.items()}

with st.expander("参数优化", expanded=True):
    st.info("第一版采用网格搜索：候选值会进行全部组合。为避免误操作，单次最多100组。")
    selected_plugin = st.selectbox(
        "策略",
        list(metadata_by_name),
        index=list(metadata_by_name).index(default_request.strategy_plugin),
        format_func=lambda name: metadata_by_name[name].display_name,
        key="optimization_strategy",
    )
    metadata = metadata_by_name[selected_plugin]
    defaults = (
        default_request.strategy_parameters
        if selected_plugin == default_request.strategy_plugin
        else metadata.defaults()
    )
    with st.form("optimization_form"):
        st.caption("每个参数可以输入多个候选值，用英文或中文逗号分隔。")
        candidate_text: dict[str, str] = {}
        columns = st.columns(2)
        for index, parameter in enumerate(metadata.parameters):
            with columns[index % 2]:
                candidate_text[parameter.name] = st.text_input(
                    parameter.label,
                    value=str(defaults[parameter.name]),
                    help=parameter.description or None,
                    key=f"optimization_{parameter.name}",
                )
        left, middle, right = st.columns(3)
        with left:
            start_date = st.date_input("开始日期", default_request.start_date, key="opt_start")
            initial_cash = st.number_input(
                "初始资金", min_value=1_000.0, value=default_request.initial_cash, key="opt_cash"
            )
        with middle:
            end_date = st.date_input("结束日期", default_request.end_date, key="opt_end")
            top_n = st.number_input(
                "最大持仓数量", min_value=1, value=default_request.top_n, step=1, key="opt_top_n"
            )
        with right:
            objective_names: list[str] = list(OBJECTIVES.keys())
            objective = st.selectbox(
                "排序指标",
                objective_names,
                format_func=lambda name: OBJECTIVES[str(name)],
                key="opt_objective",
            )
            drawdown_limit = st.number_input(
                "允许的最大回撤",
                min_value=0.0,
                max_value=1.0,
                value=0.30,
                step=0.01,
                format="%.2f",
            )
        submitted = st.form_submit_button("开始参数优化", type="primary")

    if submitted:
        try:
            grid = {
                parameter.name: _parse_candidates(parameter, candidate_text[parameter.name])
                for parameter in metadata.parameters
            }
            base = replace(
                default_request,
                strategy_plugin=selected_plugin,
                strategy_id=f"{selected_plugin}_optimization",
                strategy_parameters={name: values[0] for name, values in grid.items()},
                start_date=start_date,
                end_date=end_date,
                initial_cash=float(initial_cash),
                top_n=int(top_n),
            )
            request = OptimizationRequest(
                base_request=base,
                parameter_grid=grid,
                objective=str(objective),
                max_drawdown_limit=float(drawdown_limit),
            )
            optimizer = OptimizationService(service)
            count = optimizer.combination_count(request)
            with st.spinner(f"正在运行 {count} 组回测……"):
                result = optimizer.run(request)
            st.session_state["latest_optimization"] = str(result.output_dir / "results.csv")
            st.success(f"参数优化完成，共运行 {count} 组。")
        except Exception as exc:
            st.exception(exc)

    latest_path = st.session_state.get("latest_optimization")
    if latest_path:
        latest = pd.read_csv(latest_path)
        parameter_labels = {f"param_{item.name}": item.label for item in metadata.parameters}
        latest_display = localize_frame(latest.rename(columns=parameter_labels))
        st.dataframe(latest_display, width="stretch", hide_index=True)
        st.download_button(
            "下载优化结果 CSV",
            dataframe_to_csv_bytes(latest),
            "optimization_results.csv",
            "text/csv; charset=utf-8",
        )

with st.expander("滚动样本外验证", expanded=False):
    st.info(
        "系统只在训练期选择参数，再用紧随其后的未见数据测试；随后向前滚动，"
        "避免用同一段历史既选参数又评价参数。"
    )
    wf_plugin = st.selectbox(
        "验证策略",
        list(metadata_by_name),
        index=list(metadata_by_name).index(default_request.strategy_plugin),
        format_func=lambda name: metadata_by_name[name].display_name,
        key="walk_forward_strategy",
    )
    wf_metadata = metadata_by_name[wf_plugin]
    wf_defaults = (
        default_request.strategy_parameters
        if wf_plugin == default_request.strategy_plugin
        else wf_metadata.defaults()
    )
    with st.form("walk_forward_form"):
        st.caption("每个窗口都只使用过去的训练数据选参数，测试区间不会参与参数排名。")
        wf_candidates: dict[str, str] = {}
        wf_parameter_columns = st.columns(2)
        for index, parameter in enumerate(wf_metadata.parameters):
            with wf_parameter_columns[index % 2]:
                wf_candidates[parameter.name] = st.text_input(
                    parameter.label,
                    value=str(wf_defaults[parameter.name]),
                    help=parameter.description or None,
                    key=f"walk_forward_{parameter.name}",
                )
        wf_left, wf_middle, wf_right = st.columns(3)
        with wf_left:
            wf_start = st.date_input("总开始日期", default_request.start_date, key="wf_start")
            wf_end = st.date_input("总结束日期", default_request.end_date, key="wf_end")
        with wf_middle:
            training_months = st.number_input(
                "训练期（月）", min_value=3, value=12, step=1, key="wf_training_months"
            )
            test_months = st.number_input(
                "每次样本外测试（月）", min_value=1, value=3, step=1, key="wf_test_months"
            )
        with wf_right:
            step_months = st.number_input(
                "滚动步长（月）", min_value=1, value=3, step=1, key="wf_step_months"
            )
            max_windows = st.number_input(
                "最多窗口数", min_value=1, max_value=24, value=8, step=1, key="wf_max_windows"
            )
            wf_objective = st.selectbox(
                "训练期排序指标",
                list(OBJECTIVES),
                format_func=lambda name: OBJECTIVES[str(name)],
                key="wf_objective",
            )
        wf_submitted = st.form_submit_button("开始滚动样本外验证", type="primary")

    if wf_submitted:
        try:
            wf_grid = {
                parameter.name: _parse_candidates(parameter, wf_candidates[parameter.name])
                for parameter in wf_metadata.parameters
            }
            wf_base = replace(
                default_request,
                strategy_plugin=wf_plugin,
                strategy_id=f"{wf_plugin}_walk_forward",
                strategy_parameters={name: values[0] for name, values in wf_grid.items()},
                start_date=wf_start,
                end_date=wf_end,
            )
            wf_request = WalkForwardRequest(
                base_request=wf_base,
                parameter_grid=wf_grid,
                objective=str(wf_objective),
                training_months=int(training_months),
                test_months=int(test_months),
                step_months=int(step_months),
                max_windows=int(max_windows),
            )
            validator = WalkForwardService(service)
            windows = validator.build_windows(wf_request)
            combinations = 1
            for values in wf_grid.values():
                combinations *= len(values)
            with st.spinner(
                f"正在运行 {len(windows)} 个窗口，每个窗口训练 {combinations} 组参数……"
            ):
                wf_result = validator.run(wf_request)
            st.session_state["latest_walk_forward"] = str(wf_result.output_dir)
            st.success(
                f"滚动验证完成：{wf_result.summary['successful_windows']}/"
                f"{wf_result.summary['window_count']} 个样本外窗口成功。"
            )
        except Exception as exc:
            st.exception(exc)

    wf_path = st.session_state.get("latest_walk_forward")
    if wf_path:
        wf_directory = Path(wf_path)
        wf_results = pd.read_csv(wf_directory / "results.csv")
        wf_summary = json.loads((wf_directory / "summary.json").read_text(encoding="utf-8"))
        wf_metrics = st.columns(4)
        wf_metrics[0].metric("成功窗口", f"{wf_summary.get('successful_windows', 0)}")
        wf_metrics[1].metric(
            "样本外累计收益",
            (
                f"{float(wf_summary['out_of_sample_cumulative_return']):.2%}"
                if wf_summary.get("out_of_sample_cumulative_return") is not None
                else "—"
            ),
        )
        wf_metrics[2].metric(
            "正收益窗口比例",
            (
                f"{float(wf_summary['positive_window_ratio']):.2%}"
                if wf_summary.get("positive_window_ratio") is not None
                else "—"
            ),
        )
        wf_metrics[3].metric(
            "最差窗口回撤",
            (
                f"{float(wf_summary['worst_window_drawdown']):.2%}"
                if wf_summary.get("worst_window_drawdown") is not None
                else "—"
            ),
        )
        st.warning(str(wf_summary.get("trust_warning", "")))
        st.dataframe(localize_frame(wf_results), width="stretch", hide_index=True)
        st.download_button(
            "下载滚动验证结果 CSV",
            dataframe_to_csv_bytes(wf_results),
            "walk_forward_results.csv",
            "text/csv; charset=utf-8",
        )
st.divider()
st.header("回测结果对比")
records = service.run_store.list_records(successful_only=True)
if len(records) < 2:
    st.info("至少需要两次成功回测才能进行对比。")
else:
    record_by_id = {record.run_id: record for record in records}
    selected_ids = st.multiselect(
        "选择2～5次回测",
        list(record_by_id),
        default=list(record_by_id)[: min(2, len(record_by_id))],
        format_func=lambda run_id: _run_label(record_by_id[run_id], strategy_names),
        max_selections=5,
    )
    if len(selected_ids) < 2:
        st.warning("请至少选择两次回测。")
    else:
        comparison = service.run_store.comparison_frame(selected_ids)
        important = [
            column
            for column in [
                "run_id",
                "strategy",
                "parameters",
                "start_date",
                "end_date",
                "cumulative_return",
                "annual_return",
                "max_drawdown",
                "sharpe",
                "sortino",
                "calmar",
                "total_transaction_cost",
                "orders",
                "risk_rejections",
                "risk_adjustments",
            ]
            if column in comparison.columns
        ]
        comparison_display = comparison[important].copy()
        if "parameters" in comparison_display.columns:
            comparison_display["parameters"] = comparison_display.apply(
                lambda row: _localized_parameters(
                    row["parameters"],
                    row.get("strategy"),
                    metadata_by_name,
                ),
                axis=1,
            )
        if "strategy" in comparison_display.columns:
            comparison_display["strategy"] = comparison_display["strategy"].map(
                lambda value: strategy_names.get(str(value), value)
            )
        st.dataframe(
            localize_frame(comparison_display),
            width="stretch",
            hide_index=True,
        )
        nav = service.run_store.normalized_nav(selected_ids)
        if not nav.empty:
            st.subheader("标准化净值（起点=1）")
            nav_display = nav.rename(columns={"trade_date": "交易日期"})
            st.line_chart(nav_display.set_index("交易日期"))
        st.download_button(
            "下载对比结果 CSV",
            dataframe_to_csv_bytes(comparison),
            "backtest_comparison.csv",
            "text/csv; charset=utf-8",
        )
