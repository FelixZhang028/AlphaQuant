"""Interactive Streamlit workbench for strategy backtests and results."""

from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from quant_platform.application.backtest_service import BacktestService
from quant_platform.backtest.metrics import (
    calculate_drawdown_series,
    calculate_monthly_returns,
)
from quant_platform.strategies.spec import ParameterKind, StrategyParameter
from quant_platform.web.localization import localize_frame, rebalance_label


def _parameter_input(
    parameter: StrategyParameter, value: int | float | bool | str
) -> int | float | bool | str:
    """Render one declarative strategy parameter."""

    help_text = parameter.description or None
    key = f"strategy_parameter_{parameter.name}"
    if parameter.choices:
        choices = list(parameter.choices)
        default_index = choices.index(str(value)) if str(value) in choices else 0
        return st.selectbox(parameter.label, choices, index=default_index, help=help_text, key=key)
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
                min_value=(float(parameter.minimum) if parameter.minimum is not None else None),
                max_value=(float(parameter.maximum) if parameter.maximum is not None else None),
                help=help_text,
                key=key,
            )
        )
    if parameter.kind == ParameterKind.BOOLEAN:
        return st.checkbox(parameter.label, value=bool(value), help=help_text, key=key)
    return st.text_input(parameter.label, value=str(value), help=help_text, key=key)


def _numeric(summary: dict[str, Any], key: str) -> float | None:
    value = summary.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _display_value(summary: dict[str, Any], key: str, kind: str) -> str:
    number = _numeric(summary, key)
    if number is None:
        return "—"
    if kind == "percent":
        return f"{number:.2%}"
    if kind == "money":
        return f"{number:,.2f}"
    if kind == "integer":
        return f"{int(number):,}"
    if kind == "days":
        return f"{number:.1f} 天"
    return f"{number:.2f}"


def _render_metric_grid(summary: dict[str, Any], items: list[tuple[str, str, str]]) -> None:
    """Render a compact four-column metric grid."""

    for offset in range(0, len(items), 4):
        row = items[offset : offset + 4]
        columns = st.columns(4)
        for column, (label, key, kind) in zip(columns, row, strict=False):
            column.metric(label, _display_value(summary, key, kind))


def _read_optional_frame(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


def _render_overview(summary: dict[str, Any], nav: pd.DataFrame) -> None:
    st.subheader("净值与回撤")
    chart = nav.copy()
    chart["trade_date"] = pd.to_datetime(chart["trade_date"])
    equity_chart = chart.rename(columns={"trade_date": "交易日期", "equity": "账户权益"})
    st.line_chart(equity_chart.set_index("交易日期")[["账户权益"]])
    drawdown = calculate_drawdown_series(nav)
    if not drawdown.empty:
        drawdown_chart = drawdown.rename(columns={"trade_date": "交易日期", "drawdown": "回撤"})
        st.line_chart(drawdown_chart.set_index("交易日期")[["回撤"]])
    start = summary.get("max_drawdown_start_date") or "—"
    trough = summary.get("max_drawdown_trough_date") or "—"
    recovery = summary.get("max_drawdown_recovery_date") or "尚未恢复"
    duration = summary.get("max_drawdown_duration_trading_days", "—")
    st.caption(f"最大回撤区间：{start} → {trough}；恢复：{recovery}；持续：{duration} 个交易日。")

    st.subheader("月度收益")
    monthly = calculate_monthly_returns(nav)
    if monthly.empty:
        st.info("当前运行没有足够数据计算月度收益。")
    else:
        table = monthly.pivot(index="year", columns="month_number", values="return").reindex(
            columns=range(1, 13)
        )
        table.columns = [f"{month}月" for month in table.columns]
        table.index.name = "年份"
        st.dataframe(table.style.format("{:.2%}", na_rep="—"), width="stretch")


def _render_return_metrics(summary: dict[str, Any]) -> None:
    _render_metric_grid(
        summary,
        [
            ("累计收益", "cumulative_return", "percent"),
            ("年化收益", "annual_return", "percent"),
            ("年化波动率", "annual_volatility", "percent"),
            ("下行波动率", "downside_volatility", "percent"),
            ("夏普比率", "sharpe", "ratio"),
            ("索提诺比率", "sortino", "ratio"),
            ("卡玛比率", "calmar", "ratio"),
            ("最大回撤", "max_drawdown", "percent"),
            ("最佳单日", "best_day_return", "percent"),
            ("最差单日", "worst_day_return", "percent"),
            ("正收益日比例", "positive_day_ratio", "percent"),
            ("正收益月比例", "positive_month_ratio", "percent"),
        ],
    )


def _render_trade_metrics(summary: dict[str, Any], trades: pd.DataFrame) -> None:
    st.subheader("订单与完整交易")
    _render_metric_grid(
        summary,
        [
            ("订单数", "orders", "integer"),
            ("成交数", "fills", "integer"),
            ("订单成交率", "order_fill_rate", "percent"),
            ("拒单数", "rejected_orders", "integer"),
            ("完整交易", "closed_trades", "integer"),
            ("交易胜率", "trade_win_rate", "percent"),
            ("盈亏比", "payoff_ratio", "ratio"),
            ("盈利因子", "profit_factor", "ratio"),
            ("平均盈利", "average_win", "money"),
            ("平均亏损", "average_loss", "money"),
            ("平均持仓", "average_holding_days", "days"),
            ("年化换手率", "annualized_turnover", "percent"),
        ],
    )

    st.subheader("交易成本")
    _render_metric_grid(
        summary,
        [
            ("佣金", "commission", "money"),
            ("印花税", "stamp_tax", "money"),
            ("滑点成本", "slippage_cost", "money"),
            ("总交易成本", "total_transaction_cost", "money"),
            ("成本/初始资金", "transaction_cost_to_initial_cash", "percent"),
            ("成交金额", "traded_notional", "money"),
            ("已实现毛盈亏", "realized_gross_pnl", "money"),
            ("已实现净盈亏", "realized_net_pnl", "money"),
        ],
    )
    if trades.empty:
        st.info("没有已完成的买卖配对，或该结果来自旧版本。")
    else:
        st.subheader("完整交易明细（先进先出）")
        display_trades = localize_frame(trades.sort_values("sell_date", ascending=False))
        st.dataframe(display_trades, width="stretch", hide_index=True)


def _render_position_metrics(
    summary: dict[str, Any], nav: pd.DataFrame, positions: pd.DataFrame
) -> None:
    _render_metric_grid(
        summary,
        [
            ("平均持仓数", "average_position_count", "ratio"),
            ("最大持仓数", "max_position_count", "integer"),
            ("平均仓位", "average_exposure", "percent"),
            ("最大仓位", "max_exposure", "percent"),
            ("平均现金比例", "average_cash_ratio", "percent"),
            ("最低现金比例", "minimum_cash_ratio", "percent"),
            ("在场时间比例", "time_in_market_ratio", "percent"),
            ("单股最大权重", "max_single_position_weight", "percent"),
            ("平均集中度 HHI", "average_concentration_hhi", "ratio"),
            ("最大集中度 HHI", "max_concentration_hhi", "ratio"),
        ],
    )
    if {"trade_date", "market_value", "equity"}.issubset(nav.columns):
        exposure = nav[["trade_date", "market_value", "equity"]].copy()
        exposure["trade_date"] = pd.to_datetime(exposure["trade_date"])
        exposure["仓位"] = pd.to_numeric(exposure["market_value"], errors="coerce") / pd.to_numeric(
            exposure["equity"], errors="coerce"
        )
        st.subheader("每日仓位")
        exposure = exposure.rename(columns={"trade_date": "交易日期"})
        st.line_chart(exposure.set_index("交易日期")["仓位"])
    st.subheader("最新持仓")
    if positions.empty:
        st.info("当前为空仓。")
    else:
        latest_date = positions["trade_date"].max()
        latest_positions = positions[positions["trade_date"] == latest_date]
        st.dataframe(localize_frame(latest_positions), width="stretch", hide_index=True)


def _render_result(run_dir: Path) -> None:
    """Render persisted artifacts for one completed run."""

    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        st.warning("该运行缺少 summary.json。")
        return
    raw_summary: Any = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(raw_summary, dict):
        st.error("summary.json 格式无效。")
        return
    summary: dict[str, Any] = {str(key): value for key, value in raw_summary.items()}
    nav = pd.read_parquet(run_dir / "nav.parquet")
    positions = pd.read_parquet(run_dir / "positions.parquet")
    orders = pd.read_parquet(run_dir / "orders.parquet")
    fills = pd.read_parquet(run_dir / "fills.parquet")
    trades = _read_optional_frame(run_dir / "closed_trades.parquet")

    _render_metric_grid(
        summary,
        [
            ("最终权益", "final_equity", "money"),
            ("累计收益", "cumulative_return", "percent"),
            ("年化收益", "annual_return", "percent"),
            ("最大回撤", "max_drawdown", "percent"),
            ("夏普比率", "sharpe", "ratio"),
            ("索提诺比率", "sortino", "ratio"),
            ("卡玛比率", "calmar", "ratio"),
            ("总交易成本", "total_transaction_cost", "money"),
        ],
    )

    overview_tab, return_tab, trade_tab, position_tab, detail_tab = st.tabs(
        ["概览", "收益与风险", "交易与成本", "持仓分析", "订单明细"]
    )
    with overview_tab:
        _render_overview(summary, nav)
    with return_tab:
        _render_return_metrics(summary)
    with trade_tab:
        _render_trade_metrics(summary, trades)
    with position_tab:
        _render_position_metrics(summary, nav, positions)
    with detail_tab:
        st.subheader("订单")
        st.dataframe(localize_frame(orders.tail(200)), width="stretch", hide_index=True)
        st.subheader("成交")
        st.dataframe(localize_frame(fills.tail(200)), width="stretch", hide_index=True)


st.title("A股量化工作台")

config_path = st.sidebar.text_input("应用配置", "configs/app.yaml")
try:
    service = BacktestService(config_path)
    default_request = service.default_request()
except Exception as exc:
    st.error(f"配置或策略加载失败：{exc}")
    st.stop()

metadata_by_name = {metadata.plugin_name: metadata for metadata in service.available_strategies()}
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
            "策略实例编号",
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
                format_func=rebalance_label,
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
runs = [record.path for record in service.run_store.list_records(successful_only=True)]
if not runs:
    st.info("暂无回测结果，请先在上方运行一次回测。")
    st.stop()

preferred = st.session_state.get("selected_run")
run_index = next((index for index, path in enumerate(runs) if path.name == preferred), 0)
selected_run = st.selectbox("回测运行", runs, index=run_index, format_func=lambda path: path.name)
_render_result(selected_run)
