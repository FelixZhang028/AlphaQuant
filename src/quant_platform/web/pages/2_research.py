"""Parameter optimization and rolling out-of-sample validation."""

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
from quant_platform.web.localization import localize_frame, rebalance_label
from quant_platform.web.run_labels import format_run_label


def _parse_candidates(parameter: StrategyParameter, raw: str) -> tuple[Any, ...]:
    parts = [part.strip() for part in raw.replace("，", ",").split(",") if part.strip()]
    if not parts:
        raise ValueError(f"{parameter.label} 至少需要一个候选值")
    if parameter.kind == ParameterKind.INTEGER:
        return tuple(int(part) for part in parts)
    if parameter.kind == ParameterKind.NUMBER:
        return tuple(float(part) for part in parts)
    if parameter.kind == ParameterKind.BOOLEAN:
        aliases = {
            "true": True,
            "1": True,
            "是": True,
            "false": False,
            "0": False,
            "否": False,
        }
        try:
            return tuple(aliases[part.lower()] for part in parts)
        except KeyError as exc:
            raise ValueError(f"{parameter.label} 请填写“是,否”（也支持 true,false）") from exc
    return tuple(parts)


def _metric(value: Any, *, percent: bool = False) -> str:
    if not isinstance(value, (int, float)):
        return "—"
    return f"{float(value):.2%}" if percent else f"{float(value):.2f}"


st.title("参数优化与稳健性验证")
st.caption("从一次成功回测出发，寻找候选参数，并用未见数据检查策略是否稳定。")

config_path = st.sidebar.text_input(
    "验证配置", "configs/app.yaml", key="research_config_path"
)
try:
    service = BacktestService(config_path)
except Exception as exc:
    st.error(f"无法加载验证配置：{exc}")
    st.stop()

metadata_by_name = {item.plugin_name: item for item in service.available_strategies()}
strategy_names = {name: item.display_name for name, item in metadata_by_name.items()}
records = service.run_store.list_records(successful_only=True)
if not records:
    st.info("请先完成一次成功的单次回测，再创建验证实验。")
    if st.button("前往单次回测", type="primary"):
        st.switch_page("home.py")
    st.stop()

record_by_id = {record.run_id: record for record in records}
run_ids = list(record_by_id)
preferred = st.session_state.get("research_baseline_run_id")
baseline_index = run_ids.index(preferred) if preferred in run_ids else 0
baseline_id = st.selectbox(
    "基准回测",
    run_ids,
    index=baseline_index,
    format_func=lambda run_id: format_run_label(record_by_id[run_id], strategy_names),
    help="实验会继承该回测的策略、资金、持仓数量、调仓频率和风险配置。",
)
st.session_state["research_baseline_run_id"] = baseline_id

try:
    baseline = service.request_from_run(baseline_id)
    metadata = metadata_by_name[baseline.strategy_plugin]
    baseline_summary = service.run_store.load_summary(baseline_id)
except Exception as exc:
    st.error(f"无法读取基准回测：{exc}")
    st.stop()

with st.container(border=True):
    st.subheader("基准回测摘要")
    st.caption(
        f"{metadata.display_name}｜{baseline.start_date}～{baseline.end_date}｜"
        f"初始资金 {baseline.initial_cash:,.0f}｜最大持仓 {baseline.top_n}｜"
        f"调仓频率 {rebalance_label(baseline.rebalance)}"
    )
    summary_columns = st.columns(4)
    summary_columns[0].metric(
        "累计收益", _metric(baseline_summary.get("cumulative_return"), percent=True)
    )
    summary_columns[1].metric(
        "最大回撤", _metric(baseline_summary.get("max_drawdown"), percent=True)
    )
    summary_columns[2].metric("夏普比率", _metric(baseline_summary.get("sharpe")))
    summary_columns[3].metric("交易次数", str(baseline_summary.get("closed_trades", "—")))
    parameter_text = "；".join(
        f"{parameter.label}={baseline.strategy_parameters.get(parameter.name)}"
        for parameter in metadata.parameters
    )
    st.caption(f"基准参数：{parameter_text}")

baseline_suffix = baseline_id[:8]

with st.expander("参数优化", expanded=True):
    st.info(
        "填写每个参数的候选值，系统将运行全部组合并按目标指标排名。"
        "单次实验最多100组，以控制过拟合和运行时间。"
    )
    with st.form(f"optimization_form_{baseline_suffix}"):
        candidate_text: dict[str, str] = {}
        parameter_columns = st.columns(2)
        for index, parameter in enumerate(metadata.parameters):
            with parameter_columns[index % 2]:
                candidate_text[parameter.name] = st.text_input(
                    parameter.label,
                    value=str(baseline.strategy_parameters[parameter.name]),
                    help=parameter.description or None,
                    key=f"optimization_{baseline_suffix}_{parameter.name}",
                )
        left, middle, right = st.columns(3)
        with left:
            start_date = st.date_input(
                "实验开始日期", baseline.start_date, key=f"opt_start_{baseline_suffix}"
            )
            end_date = st.date_input(
                "实验结束日期", baseline.end_date, key=f"opt_end_{baseline_suffix}"
            )
        with middle:
            objective = st.selectbox(
                "排序指标",
                list(OBJECTIVES),
                format_func=lambda name: OBJECTIVES[str(name)],
                key=f"opt_objective_{baseline_suffix}",
            )
            drawdown_limit = st.number_input(
                "允许的最大回撤",
                min_value=0.0,
                max_value=1.0,
                value=0.30,
                step=0.01,
                format="%.2f",
                key=f"opt_drawdown_{baseline_suffix}",
            )
        with right:
            st.caption("其他设置自动继承基准回测")
            st.write(f"初始资金：{baseline.initial_cash:,.0f}")
            st.write(f"最大持仓：{baseline.top_n}")
            st.write(f"调仓频率：{rebalance_label(baseline.rebalance)}")
        submitted = st.form_submit_button("开始参数优化", type="primary")

    if submitted:
        try:
            grid = {
                parameter.name: _parse_candidates(
                    parameter, candidate_text[parameter.name]
                )
                for parameter in metadata.parameters
            }
            base = replace(
                baseline,
                strategy_id=f"{baseline.strategy_id}_optimization",
                strategy_parameters={name: values[0] for name, values in grid.items()},
                start_date=start_date,
                end_date=end_date,
            )
            request = OptimizationRequest(
                base_request=base,
                parameter_grid=grid,
                objective=str(objective),
                max_drawdown_limit=float(drawdown_limit),
                baseline_run_id=baseline_id,
            )
            optimizer = OptimizationService(service)
            count = optimizer.combination_count(request)
            with st.spinner(f"正在运行 {count} 组参数……"):
                result = optimizer.run(request)
            st.session_state[f"latest_optimization_{baseline_id}"] = str(
                result.output_dir / "results.csv"
            )
            st.success(f"参数优化完成，共运行 {count} 组。")
        except Exception as exc:
            st.exception(exc)

    latest_path = st.session_state.get(f"latest_optimization_{baseline_id}")
    if latest_path:
        latest = pd.read_csv(latest_path)
        parameter_labels = {
            f"param_{item.name}": item.label for item in metadata.parameters
        }
        st.dataframe(
            localize_frame(latest.rename(columns=parameter_labels)),
            width="stretch",
            hide_index=True,
        )
        successful_runs = latest[
            latest["status"].eq("SUCCESS") & latest["run_id"].notna()
        ]
        if not successful_runs.empty:
            child_ids = successful_runs["run_id"].astype(str).tolist()
            child_records = {
                record.run_id: record
                for record in service.run_store.list_records(successful_only=True)
                if record.run_id in set(child_ids)
            }
            child_id = st.selectbox(
                "查看参数组合的详细结果",
                child_ids,
                format_func=lambda run_id: (
                    format_run_label(child_records[run_id], strategy_names)
                    if run_id in child_records
                    else run_id
                ),
                key=f"optimization_child_{baseline_suffix}",
            )
            if st.button("打开该回测", key=f"open_opt_child_{baseline_suffix}"):
                st.session_state["selected_run"] = child_id
                st.switch_page("home.py")
        st.download_button(
            "下载优化结果 CSV",
            dataframe_to_csv_bytes(latest),
            "optimization_results.csv",
            "text/csv; charset=utf-8",
            key=f"download_opt_{baseline_suffix}",
        )

with st.expander("滚动样本外验证", expanded=False):
    st.info(
        "每个窗口只在训练期选择参数，再在紧随其后的未见数据上测试；"
        "这比直接用全区间挑选最好参数更能发现过拟合。"
    )
    with st.form(f"walk_forward_form_{baseline_suffix}"):
        wf_candidates: dict[str, str] = {}
        wf_parameter_columns = st.columns(2)
        for index, parameter in enumerate(metadata.parameters):
            with wf_parameter_columns[index % 2]:
                wf_candidates[parameter.name] = st.text_input(
                    parameter.label,
                    value=str(baseline.strategy_parameters[parameter.name]),
                    help=parameter.description or None,
                    key=f"walk_forward_{baseline_suffix}_{parameter.name}",
                )
        wf_left, wf_middle, wf_right = st.columns(3)
        with wf_left:
            wf_start = st.date_input(
                "总开始日期", baseline.start_date, key=f"wf_start_{baseline_suffix}"
            )
            wf_end = st.date_input(
                "总结束日期", baseline.end_date, key=f"wf_end_{baseline_suffix}"
            )
        with wf_middle:
            training_months = st.number_input(
                "训练期（月）",
                min_value=3,
                value=12,
                step=1,
                key=f"wf_training_{baseline_suffix}",
            )
            test_months = st.number_input(
                "样本外测试（月）",
                min_value=1,
                value=3,
                step=1,
                key=f"wf_test_{baseline_suffix}",
            )
        with wf_right:
            step_months = st.number_input(
                "滚动步长（月）",
                min_value=1,
                value=3,
                step=1,
                key=f"wf_step_{baseline_suffix}",
            )
            max_windows = st.number_input(
                "最多窗口数",
                min_value=1,
                max_value=24,
                value=8,
                step=1,
                key=f"wf_windows_{baseline_suffix}",
            )
            wf_objective = st.selectbox(
                "训练期排序指标",
                list(OBJECTIVES),
                format_func=lambda name: OBJECTIVES[str(name)],
                key=f"wf_objective_{baseline_suffix}",
            )
        wf_submitted = st.form_submit_button("开始滚动样本外验证", type="primary")

    if wf_submitted:
        try:
            wf_grid = {
                parameter.name: _parse_candidates(
                    parameter, wf_candidates[parameter.name]
                )
                for parameter in metadata.parameters
            }
            wf_base = replace(
                baseline,
                strategy_id=f"{baseline.strategy_id}_walk_forward",
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
                baseline_run_id=baseline_id,
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
            st.session_state[f"latest_walk_forward_{baseline_id}"] = str(
                wf_result.output_dir
            )
            st.success(
                f"滚动验证完成：{wf_result.summary['successful_windows']}/"
                f"{wf_result.summary['window_count']} 个样本外窗口成功。"
            )
        except Exception as exc:
            st.exception(exc)

    wf_path = st.session_state.get(f"latest_walk_forward_{baseline_id}")
    if wf_path:
        wf_directory = Path(wf_path)
        wf_results = pd.read_csv(wf_directory / "results.csv")
        wf_summary = json.loads((wf_directory / "summary.json").read_text(encoding="utf-8"))
        wf_metrics = st.columns(4)
        wf_metrics[0].metric("成功窗口", f"{wf_summary.get('successful_windows', 0)}")
        wf_metrics[1].metric(
            "样本外累计收益",
            _metric(wf_summary.get("out_of_sample_cumulative_return"), percent=True),
        )
        wf_metrics[2].metric(
            "正收益窗口比例",
            _metric(wf_summary.get("positive_window_ratio"), percent=True),
        )
        wf_metrics[3].metric(
            "最差窗口回撤",
            _metric(wf_summary.get("worst_window_drawdown"), percent=True),
        )
        st.warning(str(wf_summary.get("trust_warning", "")))
        st.dataframe(localize_frame(wf_results), width="stretch", hide_index=True)
        test_runs = wf_results.get("test_run_id", pd.Series(dtype=str)).dropna().astype(str)
        if not test_runs.empty:
            test_run_ids = test_runs.tolist()
            test_records = {
                record.run_id: record
                for record in service.run_store.list_records(successful_only=True)
                if record.run_id in set(test_run_ids)
            }
            test_run_id = st.selectbox(
                "查看样本外窗口的详细结果",
                test_run_ids,
                format_func=lambda run_id: (
                    format_run_label(test_records[run_id], strategy_names)
                    if run_id in test_records
                    else run_id
                ),
                key=f"wf_child_{baseline_suffix}",
            )
            if st.button("打开样本外回测", key=f"open_wf_child_{baseline_suffix}"):
                st.session_state["selected_run"] = test_run_id
                st.switch_page("home.py")
        st.download_button(
            "下载滚动验证结果 CSV",
            dataframe_to_csv_bytes(wf_results),
            "walk_forward_results.csv",
            "text/csv; charset=utf-8",
            key=f"download_wf_{baseline_suffix}",
        )

st.divider()
st.info("历史记录筛选与多回测对比已移至“回测记录库”，避免本页面重复承担复盘功能。")
if st.button("打开回测记录库"):
    st.switch_page("pages/6_run_library.py")
