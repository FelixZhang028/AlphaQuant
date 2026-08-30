"""Persistent end-of-day paper account interface."""

from __future__ import annotations

from quant_platform.web.theme import inject_global_css

inject_global_css()


import json
from dataclasses import replace
from datetime import date

import pandas as pd
import streamlit as st

from quant_platform.application.backtest_service import BacktestService
from quant_platform.application.paper_service import PaperTradingService
from quant_platform.web.localization import localize_frame, status_label

st.title("模拟交易")
st.caption("日线回放式模拟账户：按指定日期推进，账户配置和最新结果会长期保存在本地。")
st.info(
    "当前版本会从账户开始日重新回放到目标日期，以保证结果可重复；"
    "它不是实时行情撮合，也不会连接真实券商。"
)

config_path = "configs/app.yaml"  # 正式版固定配置路径，不再提供侧栏修改入口
try:
    backtests = BacktestService(config_path)
    papers = PaperTradingService(backtests)
    default_request = backtests.default_request()
    strategy_names = {
        item.plugin_name: item.display_name for item in backtests.available_strategies()
    }
except Exception as exc:
    st.error(f"无法加载模拟交易配置：{exc}")
    st.stop()

with st.expander("创建模拟账户", expanded=not papers.list_accounts()):
    with st.form("create_paper_account"):
        name = st.text_input("账户名称", "我的日线模拟账户")
        left, right = st.columns(2)
        with left:
            start_date = st.date_input("开始日期", default_request.start_date)
            initial_cash = st.number_input(
                "初始资金", min_value=1_000.0, value=default_request.initial_cash
            )
        with right:
            top_n = st.number_input(
                "最大持仓数量", min_value=1, value=default_request.top_n, step=1
            )
            st.text_input(
                "策略",
                strategy_names.get(
                    default_request.strategy_plugin,
                    default_request.strategy_plugin,
                ),
                disabled=True,
            )
        created = st.form_submit_button("创建账户", type="primary")
    if created:
        try:
            record = papers.create(
                name,
                replace(
                    default_request,
                    start_date=start_date,
                    initial_cash=float(initial_cash),
                    top_n=int(top_n),
                ),
            )
            st.session_state["paper_account_id"] = record.account_id
            st.success("模拟账户已创建。")
            st.rerun()
        except Exception as exc:
            st.error(f"创建失败：{exc}")

accounts = papers.list_accounts()
if not accounts:
    st.stop()
account_by_id = {account.account_id: account for account in accounts}

# 清理失效的 session_state 值，避免 selectbox 因 key 对应无效值而异常
preferred = st.session_state.get("paper_account_id")
if preferred is not None and preferred not in account_by_id:
    del st.session_state["paper_account_id"]

selected_id = st.selectbox(
    "模拟账户",
    list(account_by_id),
    format_func=lambda account_id: (
        f"{account_by_id[account_id].display_name} | "
        f"{status_label(account_by_id[account_id].status)} | {account_id}"
    ),
    key="paper_account_id",
)
account = account_by_id[selected_id]
request = account.request

status, strategy, last_date = st.columns(3)
status.metric("状态", status_label(account.status))
strategy.metric(
    "策略",
    strategy_names.get(str(request["strategy_plugin"]), str(request["strategy_plugin"])),
)
last_date.metric("已推进至", account.last_date or "尚未运行")
if account.error:
    st.error(account.error)

checklist = papers.go_live_checklist(account.account_id)
with st.expander("上线前检查清单", expanded=checklist.blocked):
    icons = {"blocker": "❌", "warning": "⚠️", "info": "ℹ️"}
    for item in checklist.items:
        icon = "✅" if item.passed else icons.get(item.severity, "⚠️")
        st.markdown(f"{icon} **{item.title}**：{item.detail}")
if checklist.blocked:
    st.warning("存在未通过的阻断项，请先处理后再推进模拟账户。")

with st.form("advance_paper_account"):
    target_date = st.date_input("推进至日期", value=date.today())
    advanced = st.form_submit_button(
        "运行模拟交易", type="primary", disabled=checklist.blocked
    )
if advanced:
    try:
        with st.spinner("正在推进模拟账户……"):
            papers.advance(account.account_id, target_date)
        st.success("模拟账户推进完成。")
        st.rerun()
    except Exception as exc:
        st.exception(exc)

run_dir = papers.latest_run_dir(account)
if run_dir is not None:
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    columns = st.columns(4)
    columns[0].metric("当前权益", f"{float(summary.get('final_equity', 0)):,.2f}")
    columns[1].metric("累计收益", f"{float(summary.get('cumulative_return', 0)):.2%}")
    columns[2].metric("最大回撤", f"{float(summary.get('max_drawdown', 0)):.2%}")
    columns[3].metric("风控拒绝", f"{int(summary.get('risk_rejections', 0)):,}")
    nav = pd.read_parquet(run_dir / "nav.parquet")
    equity_curve = nav.rename(columns={"trade_date": "交易日期", "equity": "账户权益"}).set_index(
        "交易日期"
    )[["账户权益"]]
    st.line_chart(equity_curve)
    position_tab, order_tab, risk_tab = st.tabs(["当前持仓", "委托与成交", "风控记录"])
    with position_tab:
        positions = pd.read_parquet(run_dir / "positions.parquet")
        if positions.empty:
            st.info("当前为空仓。")
        else:
            latest = positions[positions["trade_date"].eq(positions["trade_date"].max())]
            st.dataframe(localize_frame(latest), width="stretch", hide_index=True)
    with order_tab:
        orders = pd.read_parquet(run_dir / "orders.parquet")
        fills = pd.read_parquet(run_dir / "fills.parquet")
        st.subheader("委托")
        st.dataframe(localize_frame(orders.tail(200)), width="stretch", hide_index=True)
        st.subheader("成交")
        st.dataframe(localize_frame(fills.tail(200)), width="stretch", hide_index=True)
    with risk_tab:
        risk_path = run_dir / "risk_events.parquet"
        risk_events = pd.read_parquet(risk_path) if risk_path.exists() else pd.DataFrame()
        st.dataframe(localize_frame(risk_events.tail(200)), width="stretch", hide_index=True)
