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
from quant_platform.backtest.diagnosis import generate_diagnosis
from quant_platform.backtest.metrics import (
    calculate_drawdown_series,
    calculate_monthly_returns,
)
from quant_platform.backtest.result import BacktestResult
from quant_platform.backtest.validity import load_persisted_validity
from quant_platform.core.exceptions import BacktestValidityError
from quant_platform.strategies.spec import ParameterKind, StrategyParameter
from quant_platform.web.localization import localize_frame, rebalance_label
from quant_platform.web.run_labels import format_run_label


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


def _load_validity(run_dir: Path) -> dict[str, Any]:
    """Load a current report; old reports fail closed as unverified."""

    return load_persisted_validity(run_dir)


def _render_validity(report: dict[str, Any]) -> None:
    """Show the trust status before any performance number is displayed."""

    status = str(report.get("status", "WARNING"))
    reliable = bool(report.get("metrics_reliable", status != "INVALID"))
    if status == "INVALID" or not reliable:
        st.error("回测可信度：无效。以下指标仍会展示，但只能用于排查，不能用来评价策略。")
    elif status == "WARNING":
        st.warning("回测可信度：有警告。可以用于研究，但不能直接作为实盘依据。")
    else:
        st.success("回测可信度：有效。已通过当前版本的程序检查。")
    issues = report.get("issues", [])
    for issue in issues if isinstance(issues, list) else []:
        if not isinstance(issue, dict):
            continue
        message = str(issue.get("message", ""))
        if issue.get("severity") == "ERROR":
            st.error(message)
        else:
            st.caption(f"⚠️ {message}")
    maximum_gap = report.get("maximum_calendar_gap_days")
    if maximum_gap is not None:
        st.caption(f"净值日期最大间隔：{maximum_gap} 天。")
    unknown_rows = int(report.get("unknown_market_rows", 0) or 0)
    unknown_symbols = int(report.get("unknown_market_symbols", 0) or 0)
    unknown_orders = int(report.get("unknown_status_orders", 0) or 0)
    if unknown_rows:
        st.caption(
            f"交易状态未知：{unknown_rows:,} 行，涉及 {unknown_symbols:,} 只股票。"
        )
    if unknown_orders:
        st.caption(f"因交易状态未知被拒绝的订单：{unknown_orders:,} 笔。")


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


def _render_diagnosis(
    run_dir: Path,
    summary: dict[str, Any],
    nav: pd.DataFrame,
    orders: pd.DataFrame,
    fills: pd.DataFrame,
    trades: pd.DataFrame,
    positions: pd.DataFrame,
    validity: dict[str, Any],
) -> None:
    """Render the plain-language diagnosis in a collapsed expander."""

    result = BacktestResult(
        run_id=run_dir.name,
        nav=nav,
        signals=_read_optional_frame(run_dir / "signals.parquet"),
        targets=_read_optional_frame(run_dir / "target_positions.parquet"),
        orders=orders,
        fills=fills,
        trades=trades,
        positions=positions,
        risk_events=_read_optional_frame(run_dir / "risk_events.parquet"),
        summary=summary,
        validity=validity,
    )
    report = generate_diagnosis(result)
    with st.expander("通俗诊断", expanded=False):
        st.caption("以下内容为基于回测数据的通俗解读，仅供参考，不构成投资建议。")
        for section in report.sections:
            st.markdown(f"**{section.title}**")
            for bullet in section.bullets:
                st.markdown(f"- {bullet}")


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
    validity = _load_validity(run_dir)
    _render_validity(validity)

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

    _render_diagnosis(run_dir, summary, nav, orders, fills, trades, positions, validity)

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


st.title("单次回测与复盘")
st.caption("运行一组确定参数，并深入检查收益、风险、交易成本、持仓和订单。")

config_path = st.sidebar.text_input("应用配置", "configs/app.yaml")
try:
    service = BacktestService(config_path)
    default_request = service.default_request()
except Exception as exc:
    st.error(f"配置或策略加载失败：{exc}")
    st.stop()

metadata_by_name = {metadata.plugin_name: metadata for metadata in service.available_strategies()}
plugin_names = list(metadata_by_name)
strategy_names = {name: metadata.display_name for name, metadata in metadata_by_name.items()}
default_index = (
    plugin_names.index(default_request.strategy_plugin)
    if default_request.strategy_plugin in plugin_names
    else 0
)

# 因子研究室「一键转换成选股策略」跳转过来时，自动选中因子合成策略并带入参数。
factor_payload = st.session_state.pop("factor_composite_payload", None)
factor_payload_values: dict[str, Any] | None = None
if factor_payload and "factor_composite" in plugin_names:
    default_index = plugin_names.index("factor_composite")
    factor_payload_values = {
        "factors_json": json.dumps(factor_payload, ensure_ascii=False)
    }
    st.info("已从因子研究室带入合成因子参数，确认区间后点击「运行回测」。")

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
    if factor_payload_values and selected_plugin == "factor_composite":
        configured_values = {**configured_values, **factor_payload_values}
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
            st.success(
                f"回测完成：{metadata.display_name}｜区间 {start_date}～{end_date}｜"
                f"{completed.output_dir.name[:8]}"
            )
        except BacktestValidityError as exc:
            st.error(f"回测已停止：{exc}")
            st.info("请缩短回测区间或补齐相关日期后再运行。")
        except Exception as exc:
            st.exception(exc)

st.divider()
st.header("回测结果")
records = service.run_store.list_records(successful_only=True)
if not records:
    st.info("暂无回测结果，请先在上方运行一次回测。")
    st.stop()

record_by_id = {record.run_id: record for record in records}
preferred = st.session_state.get("selected_run")
run_ids = list(record_by_id)
run_index = run_ids.index(preferred) if preferred in run_ids else 0
selected_id = st.selectbox(
    "回测运行",
    run_ids,
    index=run_index,
    format_func=lambda run_id: format_run_label(record_by_id[run_id], strategy_names),
)
selected_record = record_by_id[selected_id]
st.caption(format_run_label(selected_record, strategy_names))
actions = st.columns(2)
if actions[0].button("用本次结果创建验证实验", type="primary"):
    st.session_state["research_baseline_run_id"] = selected_id
    st.switch_page("pages/2_research.py")
if actions[1].button("打开回测记录库"):
    st.switch_page("pages/6_run_library.py")
_render_result(selected_record.path)
