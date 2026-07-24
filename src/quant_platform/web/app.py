"""Interactive Streamlit workbench for strategy backtests and results."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from quant_platform.application.backtest_service import BacktestService
from quant_platform.strategies.spec import ParameterKind, StrategyParameter


def _parameter_input(
    parameter: StrategyParameter, value: int | float | bool | str
) -> int | float | bool | str:
    """Render one declarative strategy parameter."""

    help_text = parameter.description or None
    key = f"strategy_parameter_{parameter.name}"
    if parameter.choices:
        choices = list(parameter.choices)
        default_index = choices.index(str(value)) if str(value) in choices else 0
        return st.selectbox(
            parameter.label, choices, index=default_index, help=help_text, key=key
        )
    if parameter.kind == ParameterKind.INTEGER:
        return int(
            st.number_input(
                parameter.label,
                value=int(value),
                min_value=(int(parameter.minimum) if parameter.minimum is not None else None),
                max_value=(int(parameter.maximum) if parameter.maximum is not None else None),
                step=1,
                help=help_text,
                key=key,
            )
        )
    if parameter.kind == ParameterKind.NUMBER:
        return float(
            st.number_input(
                parameter.label,
                value=float(value),
                min_value=(
                    float(parameter.minimum) if parameter.minimum is not None else None
                ),
                max_value=(
                    float(parameter.maximum) if parameter.maximum is not None else None
                ),
                help=help_text,
                key=key,
            )
        )
    if parameter.kind == ParameterKind.BOOLEAN:
        return st.checkbox(parameter.label, value=bool(value), help=help_text, key=key)
    return st.text_input(
        parameter.label, value=str(value), help=help_text, key=key
    )


def _render_result(run_dir: Path) -> None:
    """Render persisted artifacts for one completed run."""

    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        st.warning("该运行缺少 summary.json。")
        return
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    columns = st.columns(4)
    columns[0].metric("最终权益", f"{summary.get('final_equity', 0):,.2f}")
    columns[1].metric("累计收益", f"{summary.get('cumulative_return', 0):.2%}")
    columns[2].metric("最大回撤", f"{summary.get('max_drawdown', 0):.2%}")
    columns[3].metric("成交笔数", int(summary.get("fills", 0)))

    nav = pd.read_parquet(run_dir / "nav.parquet")
    st.subheader("净值")
    st.line_chart(nav.set_index("trade_date")["equity"])

    positions = pd.read_parquet(run_dir / "positions.parquet")
    orders = pd.read_parquet(run_dir / "orders.parquet")
    fills = pd.read_parquet(run_dir / "fills.parquet")
    left, right = st.columns(2)
    with left:
        st.subheader("最新持仓")
        if positions.empty:
            st.info("当前为空仓。")
        else:
            latest_date = positions["trade_date"].max()
            st.dataframe(
                positions[positions["trade_date"] == latest_date],
                use_container_width=True,
            )
    with right:
        st.subheader("订单")
        st.dataframe(orders.tail(100), use_container_width=True)
    st.subheader("成交")
    st.dataframe(fills.tail(100), use_container_width=True)


st.set_page_config(page_title="A股量化工作台", layout="wide")
st.title("A股量化工作台")

config_path = st.sidebar.text_input("应用配置", "configs/app.yaml")
try:
    service = BacktestService(config_path)
    default_request = service.default_request()
except Exception as exc:
    st.error(f"配置或策略加载失败：{exc}")
    st.stop()

metadata_by_name = {
    metadata.plugin_name: metadata for metadata in service.available_strategies()
}
plugin_names = list(metadata_by_name)
default_index = (
    plugin_names.index(default_request.strategy_plugin)
    if default_request.strategy_plugin in plugin_names
    else 0
)

with st.expander("新建回测", expanded=True):
    selected_plugin = st.selectbox(
        "策略",
        plugin_names,
        index=default_index,
        format_func=lambda name: metadata_by_name[name].display_name,
    )
    metadata = metadata_by_name[selected_plugin]
    st.caption(metadata.description)
    configured_values = (
        default_request.strategy_parameters
        if selected_plugin == default_request.strategy_plugin
        else metadata.defaults()
    )
    with st.form("backtest_form"):
        strategy_id = st.text_input(
            "策略实例 ID",
            value=(
                default_request.strategy_id
                if selected_plugin == default_request.strategy_plugin
                else f"{selected_plugin}_web"
            ),
        )
        parameter_values: dict[str, Any] = {}
        parameter_columns = st.columns(2)
        for index, parameter in enumerate(metadata.parameters):
            with parameter_columns[index % 2]:
                parameter_values[parameter.name] = _parameter_input(
                    parameter, configured_values[parameter.name]
                )
        left, middle, right = st.columns(3)
        with left:
            start_date = st.date_input("开始日期", default_request.start_date)
            initial_cash = st.number_input(
                "初始资金", min_value=1_000.0, value=default_request.initial_cash
            )
        with middle:
            end_date = st.date_input("结束日期", default_request.end_date)
            top_n = st.number_input(
                "最大持仓数量", min_value=1, value=default_request.top_n, step=1
            )
        with right:
            rebalance_options = ["daily", "weekly", "monthly"]
            rebalance = st.selectbox(
                "调仓频率",
                rebalance_options,
                index=rebalance_options.index(default_request.rebalance),
            )
        submitted = st.form_submit_button("运行回测", type="primary")

    if submitted:
        request = replace(
            default_request,
            strategy_plugin=selected_plugin,
            strategy_id=strategy_id,
            strategy_parameters=parameter_values,
            start_date=start_date,
            end_date=end_date,
            initial_cash=float(initial_cash),
            top_n=int(top_n),
            rebalance=rebalance,
        )
        try:
            with st.spinner("正在运行回测……"):
                completed = service.run(request)
            st.session_state["selected_run"] = completed.output_dir.name
            st.success(f"回测完成：{completed.output_dir.name}")
        except Exception as exc:
            st.exception(exc)

st.divider()
st.header("回测结果")
runs = sorted(
    (path for path in service.runs_root.glob("*") if path.is_dir()), reverse=True
)
if not runs:
    st.info("暂无回测结果，请先在上方运行一次回测。")
    st.stop()

preferred = st.session_state.get("selected_run")
run_index = next(
    (index for index, path in enumerate(runs) if path.name == preferred), 0
)
selected_run = st.selectbox(
    "回测运行", runs, index=run_index, format_func=lambda path: path.name
)
_render_result(selected_run)
