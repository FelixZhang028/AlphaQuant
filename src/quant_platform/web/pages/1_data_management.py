"""Streamlit page for local market-data updates and quality inspection."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from quant_platform.application.data_service import DataCenterService
from quant_platform.data.network import friendly_data_error
from quant_platform.web.exports import dataframe_to_csv_bytes


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
st.caption("更新 AkShare 数据、检查覆盖率，并记录每次数据批次。")

config_path = st.sidebar.text_input(
    "数据管理配置", "configs/app.yaml", key="data_config_path"
)
try:
    service = DataCenterService(config_path)
    overview = service.overview()
except Exception as exc:
    st.error(f"数据中心加载失败：{friendly_data_error(exc)}")
    st.stop()

market = overview.market
columns = st.columns(5)
columns[0].metric("证券主表", f"{overview.security_count:,}")
columns[1].metric("配置股票", overview.configured_symbol_count)
columns[2].metric("行情覆盖率", f"{market.coverage_ratio:.2%}")
columns[3].metric("行情记录", f"{market.rows:,}")
columns[4].metric("未知状态记录", f"{market.unknown_status_rows:,}")

with st.expander("更新数据", expanded=True):
    with st.form("data_update_form"):
        left, right = st.columns(2)
        with left:
            start_date = st.date_input(
                "开始日期", value=date.today() - timedelta(days=365)
            )
            include_security_master = st.checkbox("更新全 A 证券主表", value=True)
            include_market = st.checkbox("更新配置股票池行情", value=True)
        with right:
            end_date = st.date_input("结束日期", value=date.today())
            include_benchmark = st.checkbox(
                f"更新基准 {overview.benchmark_symbol}", value=True
            )
            st.info(
                "行情更新默认只处理配置股票池，不会下载全市场历史行情。"
                "代理连接失败时会自动尝试直连。"
            )
        submitted = st.form_submit_button("开始更新", type="primary")

    if submitted:
        if start_date > end_date:
            st.warning("开始日期不能晚于结束日期。")
        elif not any((include_security_master, include_market, include_benchmark)):
            st.warning("请至少选择一个数据集。")
        else:
            try:
                with st.spinner("正在下载和校验数据……"):
                    results = service.update_all(
                        start_date,
                        end_date,
                        include_security_master=include_security_master,
                        include_market=include_market,
                        include_benchmark=include_benchmark,
                    )
                st.session_state["last_data_update"] = [
                    asdict(result) for result in results
                ]
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
        st.dataframe(result_frame, width="stretch", hide_index=True)
        _download_csv(
            result_frame,
            label="下载更新结果 CSV",
            file_name="data_update_results.csv",
            key="download_update_results_csv",
        )

coverage_tab, benchmark_tab, master_tab, versions_tab = st.tabs(
    ["覆盖率", "基准行情", "证券主表", "数据版本"]
)

with coverage_tab:
    st.subheader("配置股票池覆盖率")
    if overview.per_symbol.empty:
        st.info("暂无本地行情，请先运行数据更新。")
    else:
        st.dataframe(
            overview.per_symbol.style.format({"coverage_ratio": "{:.2%}"}),
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

with benchmark_tab:
    st.subheader(overview.benchmark_symbol)
    if overview.benchmark_bars.empty:
        st.info("暂无基准行情。")
    else:
        selected = overview.benchmark_bars[
            overview.benchmark_bars["symbol"].eq(overview.benchmark_symbol)
        ]
        st.line_chart(selected.set_index("trade_date")["raw_close"])
        st.dataframe(selected.tail(100), width="stretch")
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
        st.dataframe(overview.security_master.head(2000), width="stretch")
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
        st.dataframe(version_frame, width="stretch")
        _download_csv(
            version_frame,
            label="下载数据版本 CSV",
            file_name="data_versions.csv",
            key="download_data_versions_csv",
        )
