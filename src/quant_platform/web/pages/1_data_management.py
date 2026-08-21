"""Streamlit page for local market-data updates and quality inspection."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from quant_platform.application.data_service import DataCenterService
from quant_platform.data.network import friendly_data_error
from quant_platform.web.exports import dataframe_to_csv_bytes
from quant_platform.web.localization import localize_frame


def _download_csv(
    frame: pd.DataFrame,
    *,
    label: str,
    file_name: str,
    key: str,
) -> None:
    """Render an Excel-friendly CSV download button."""

    st.download_button(
        label=label,
        data=dataframe_to_csv_bytes(frame),
        file_name=file_name,
        mime="text/csv; charset=utf-8",
        key=key,
    )


st.title("数据管理")
st.caption("按 iFinD → AkShare 的优先顺序更新行情，检查覆盖率并记录数据版本。")

config_path = st.sidebar.text_input("数据管理配置", "configs/app.yaml", key="data_config_path")
try:
    service = DataCenterService(config_path)
    overview = service.overview()
except Exception as exc:
    st.error(f"数据中心加载失败：{friendly_data_error(exc)}")
    st.stop()

market = overview.market
source_status = service.market_source_status()
provider_labels = {
    str(row["provider"]): str(row["display_name"])
    for _, row in source_status.iterrows()
}
last_market_source = "暂无"
if not overview.manifests.empty:
    successful_market = overview.manifests[
        overview.manifests["dataset"].eq("daily_bars")
        & overview.manifests["status"].eq("SUCCESS")
    ]
    if not successful_market.empty:
        source = str(successful_market.iloc[0]["source"])
        last_market_source = provider_labels.get(source, source)
# ── 核心指标概览卡片 ──────────────────────────────────────────────
with st.container(border=True):
    st.caption("数据中心概览")
    columns = st.columns(6)
    columns[0].metric("证券主表", f"{overview.security_count:,}")
    columns[1].metric("配置股票", overview.configured_symbol_count)
    columns[2].metric("行情覆盖率", f"{market.coverage_ratio:.2%}")
    columns[3].metric("行情记录", f"{market.rows:,}")
    columns[4].metric("未知状态记录", f"{market.unknown_status_rows:,}")
    columns[5].metric("最近行情来源", last_market_source)

with st.expander("行情数据源", expanded=True):
    if not source_status.empty:
        primary = source_status.iloc[0]
        primary_name = provider_labels.get(str(primary["provider"]), str(primary["provider"]))
        if primary["readiness"] == "READY":
            st.success(f"首选数据源 {primary_name} 已配置。")
        else:
            st.warning(
                f"首选数据源 {primary_name} 尚未就绪；更新行情时会自动尝试备用数据源。"
            )
        st.dataframe(localize_frame(source_status), width="stretch", hide_index=True)
        st.caption("这里显示的是本机配置状态；实际成功来源以本次更新结果和数据版本为准。")

with st.expander("更新数据", expanded=True):
    with st.form("data_update_form"):
        left, right = st.columns(2)
        with left:
            start_date = st.date_input("开始日期", value=date.today() - timedelta(days=365))
            include_security_master = st.checkbox("更新全 A 证券主表", value=True)
            include_market = st.checkbox("更新配置股票池行情", value=True)
        with right:
            end_date = st.date_input("结束日期", value=date.today())
            include_benchmark = st.checkbox(f"更新基准 {overview.benchmark_symbol}", value=True)
            st.info(
                "行情更新默认只处理配置股票池，不会下载全市场历史行情。"
                "证券主表和基准指数目前仍固定使用 AkShare。"
            )
        configured_sources = source_status["provider"].astype(str).tolist()
        automatic_route = " → ".join(
            provider_labels.get(source, source) for source in configured_sources
        )
        source_options = ["auto", *configured_sources]
        source_choice = st.selectbox(
            "股票日线行情来源",
            source_options,
            format_func=lambda source: (
                f"自动推荐（{automatic_route}）"
                if source == "auto"
                else provider_labels.get(source, source)
            ),
            help="指定来源只影响本次股票日线更新，不修改全局默认配置。",
        )
        fallback_selected = st.checkbox(
            "首选来源失败时自动尝试其他来源",
            value=True,
            help="关闭后，如果所选或默认首选来源失败，本次股票行情更新将直接失败。",
        )
        if source_choice != "auto":
            selected_status = source_status[source_status["provider"].eq(source_choice)]
            if not selected_status.empty and selected_status.iloc[0]["readiness"] != "READY":
                st.warning(
                    f"{provider_labels.get(source_choice, source_choice)} 当前未就绪。"
                    "如保留自动回退，系统仍会尝试其他来源。"
                )
        submitted = st.form_submit_button("开始更新", type="primary")

    if submitted:
        if start_date > end_date:
            st.warning("开始日期不能晚于结束日期。")
        elif not any((include_security_master, include_market, include_benchmark)):
            st.warning("请至少选择一个数据集。")
        else:
            market_source_order: list[str] | None = None
            if source_choice != "auto":
                market_source_order = [source_choice]
                if fallback_selected:
                    market_source_order.extend(
                        source
                        for source in configured_sources
                        if source != source_choice
                    )
            try:
                with st.spinner("正在下载和校验数据……"):
                    results = service.update_all(
                        start_date,
                        end_date,
                        include_security_master=include_security_master,
                        include_market=include_market,
                        include_benchmark=include_benchmark,
                        market_source_order=market_source_order,
                        allow_market_fallback=fallback_selected,
                    )
                st.session_state["last_data_update"] = [asdict(result) for result in results]
                st.rerun()
            except Exception as exc:
                st.error(f"数据更新未能启动：{friendly_data_error(exc)}")

    last_update = st.session_state.get("last_data_update")
    if last_update:
        failed = [item for item in last_update if item["status"] == "FAILED"]
        if failed:
            names = "、".join(str(item["dataset"]) for item in failed)
            st.error(f"本次有 {len(failed)} 个数据集更新失败：{names}")
            for item in failed:
                st.caption(f"{item['dataset']}：{item['error']}")
        else:
            st.success("本次所选数据均更新完成。")
        market_results = [item for item in last_update if item["dataset"] == "daily_bars"]
        if market_results and market_results[0]["status"] == "SUCCESS":
            st.info(str(market_results[0]["message"]))
        result_frame = pd.DataFrame(last_update).rename(
            columns={
                "dataset": "数据集",
                "version_id": "版本号",
                "status": "状态",
                "rows": "记录数",
                "message": "结果",
                "error": "错误说明",
            }
        )
        st.dataframe(localize_frame(result_frame), width="stretch", hide_index=True)
        _download_csv(
            result_frame,
            label="下载更新结果 CSV",
            file_name="data_update_results.csv",
            key="download_update_results_csv",
        )

coverage_tab, market_tab, benchmark_tab, master_tab, versions_tab = st.tabs(
    ["覆盖率", "股票行情", "基准行情", "证券主表", "数据版本"]
)

with coverage_tab:
    st.subheader("配置股票池覆盖率")
    if overview.per_symbol.empty:
        st.info("暂无本地行情，请先运行数据更新。")
    else:
        coverage_display = localize_frame(overview.per_symbol)
        st.dataframe(
            coverage_display.style.format({"覆盖率": "{:.2%}"}),
            width="stretch",
        )
        _download_csv(
            overview.per_symbol,
            label="下载覆盖率 CSV",
            file_name="configured_stock_coverage.csv",
            key="download_coverage_csv",
        )
    if market.start_date and market.end_date:
        st.caption(
            f"本地范围：{market.start_date} 至 {market.end_date}；"
            f"缺失估算：{market.missing_rows:,} 行；重复：{market.duplicate_rows:,} 行。"
        )

with market_tab:
    st.subheader("配置股票池日线行情")
    daily_bars = service.repository.read_table("daily_bars")
    if daily_bars.empty:
        st.info("暂无股票行情，请先运行数据更新。")
    else:
        daily_bars = daily_bars.copy()
        daily_bars["trade_date"] = pd.to_datetime(daily_bars["trade_date"])
        available_symbols = sorted(daily_bars["symbol"].dropna().astype(str).unique())
        selected_symbols = st.multiselect(
            "股票代码",
            available_symbols,
            default=available_symbols[:1],
            key="daily_bars_export_symbols",
        )
        minimum_date = daily_bars["trade_date"].min().date()
        maximum_date = daily_bars["trade_date"].max().date()
        left, right = st.columns(2)
        with left:
            export_start = st.date_input(
                "导出开始日期",
                minimum_date,
                min_value=minimum_date,
                max_value=maximum_date,
                key="daily_bars_export_start",
            )
        with right:
            export_end = st.date_input(
                "导出结束日期",
                maximum_date,
                min_value=minimum_date,
                max_value=maximum_date,
                key="daily_bars_export_end",
            )
        selected_bars = daily_bars[
            daily_bars["symbol"].astype(str).isin(selected_symbols)
            & daily_bars["trade_date"].between(pd.Timestamp(export_start), pd.Timestamp(export_end))
        ].sort_values(["symbol", "trade_date"])
        st.caption(
            f"筛选结果 {len(selected_bars):,} 行；页面最多预览最后500行，下载包含全部筛选结果。"
        )
        st.dataframe(localize_frame(selected_bars.tail(500)), width="stretch", hide_index=True)
        if selected_bars.empty:
            st.warning("当前筛选条件没有数据。")
        else:
            _download_csv(
                selected_bars,
                label="下载股票日线行情 CSV",
                file_name="daily_bars_selected.csv",
                key="download_daily_bars_csv",
            )


with benchmark_tab:
    st.subheader(overview.benchmark_symbol)
    if overview.benchmark_bars.empty:
        st.info("暂无基准行情。")
    else:
        selected = overview.benchmark_bars[
            overview.benchmark_bars["symbol"].eq(overview.benchmark_symbol)
        ]
        closing_price = selected.rename(
            columns={"trade_date": "交易日期", "raw_close": "收盘价"}
        ).set_index("交易日期")[["收盘价"]]
        st.line_chart(closing_price)
        st.dataframe(localize_frame(selected.tail(100)), width="stretch")
        _download_csv(
            selected,
            label="下载完整基准行情 CSV",
            file_name=f"benchmark_{overview.benchmark_symbol.replace('.', '_')}.csv",
            key="download_benchmark_csv",
        )

with master_tab:
    if overview.security_master.empty:
        st.info("暂无证券主表。")
    else:
        st.dataframe(localize_frame(overview.security_master.head(2000)), width="stretch")
        st.caption("页面最多展示前 2000 行，下载文件包含完整数据。")
        _download_csv(
            overview.security_master,
            label="下载完整证券主表 CSV",
            file_name="security_master.csv",
            key="download_security_master_csv",
        )

with versions_tab:
    if overview.manifests.empty:
        st.info("暂无数据版本记录。")
    else:
        display_columns = [
            column
            for column in (
                "version_id",
                "dataset",
                "source",
                "requested_route",
                "fallback_enabled",
                "provider_route",
                "fallback_used",
                "status",
                "completed_at",
                "row_count",
                "symbol_count",
                "min_date",
                "max_date",
                "error",
            )
            if column in overview.manifests.columns
        ]
        version_frame = overview.manifests[display_columns]
        st.dataframe(localize_frame(version_frame), width="stretch")
        _download_csv(
            version_frame,
            label="下载数据版本 CSV",
            file_name="data_versions.csv",
            key="download_data_versions_csv",
        )
