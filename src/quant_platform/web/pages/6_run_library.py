"""Search, compare, and reopen persisted backtest runs."""

from __future__ import annotations

import streamlit as st

from quant_platform.application.backtest_service import BacktestService
from quant_platform.backtest.run_store import RunStatus
from quant_platform.web.exports import dataframe_to_csv_bytes
from quant_platform.web.localization import localize_frame, status_label
from quant_platform.web.run_comparison import (
    RUN_KIND_LABELS,
    comparison_display_frame,
    run_catalog_frame,
)
from quant_platform.web.run_labels import format_run_label

st.title("回测记录库")
st.caption("统一管理单次回测、参数优化和样本外验证结果，并选择多个结果进行比较。")

config_path = st.sidebar.text_input(
    "回测记录配置", "configs/app.yaml", key="run_library_config_path"
)
try:
    service = BacktestService(config_path)
except Exception as exc:
    st.error(f"无法加载回测记录：{exc}")
    st.stop()

metadata_by_name = {item.plugin_name: item for item in service.available_strategies()}
strategy_names = {name: item.display_name for name, item in metadata_by_name.items()}
records = service.run_store.list_records()
if not records:
    st.info("暂无回测记录，请先运行一次单次回测。")
    st.stop()

catalog = run_catalog_frame(records, strategy_names)
validity_summary: dict[str, dict[str, object]] = {}
for record in records:
    if record.status != RunStatus.SUCCESS:
        continue
    try:
        summary = service.run_store.load_summary(record.run_id)
    except Exception:
        continue
    validity_summary[record.run_id] = {
        "validity_status": summary.get("validity_status", "INVALID"),
        "metrics_reliable": bool(summary.get("metrics_reliable", False)),
        "legacy_unverified": bool(summary.get("legacy_unverified", True)),
    }
catalog["validity_status"] = catalog["run_id"].map(
    lambda run_id: validity_summary.get(str(run_id), {}).get("validity_status", "—")
)
catalog["metrics_reliable"] = catalog["run_id"].map(
    lambda run_id: validity_summary.get(str(run_id), {}).get("metrics_reliable", False)
)
catalog["legacy_unverified"] = catalog["run_id"].map(
    lambda run_id: validity_summary.get(str(run_id), {}).get("legacy_unverified", False)
)
successful_count = int(catalog["status"].eq(RunStatus.SUCCESS.value).sum())
failed_count = int(catalog["status"].eq(RunStatus.FAILED.value).sum())
single_count = int(catalog["run_kind"].eq("single").sum())
experiment_count = len(catalog) - single_count
legacy_count = int(catalog["legacy_unverified"].eq(True).sum())
metrics = st.columns(5)
metrics[0].metric("全部记录", len(catalog))
metrics[1].metric("成功", successful_count)
metrics[2].metric("失败", failed_count)
metrics[3].metric("旧版未验证", legacy_count)
metrics[4].metric("实验子回测", experiment_count)

with st.expander("筛选记录", expanded=True):
    filter_columns = st.columns(4)
    with filter_columns[0]:
        strategy_filter = st.multiselect(
            "策略", sorted(catalog["strategy"].dropna().astype(str).unique())
        )
    with filter_columns[1]:
        kind_options = sorted(catalog["run_kind"].dropna().astype(str).unique())
        kind_filter = st.multiselect(
            "运行类型",
            kind_options,
            format_func=lambda value: RUN_KIND_LABELS.get(value, value),
        )
    with filter_columns[2]:
        status_options = sorted(catalog["status"].dropna().astype(str).unique())
        status_filter = st.multiselect(
            "状态",
            status_options,
            default=[RunStatus.SUCCESS.value] if RunStatus.SUCCESS.value in status_options else [],
            format_func=status_label,
        )
    with filter_columns[3]:
        keyword = st.text_input("搜索名称或编号").strip().lower()

filtered = catalog.copy()
if strategy_filter:
    filtered = filtered[filtered["strategy"].isin(strategy_filter)]
if kind_filter:
    filtered = filtered[filtered["run_kind"].isin(kind_filter)]
if status_filter:
    filtered = filtered[filtered["status"].isin(status_filter)]
if keyword:
    text = filtered[["run_id", "run_label", "strategy_id"]].fillna("").astype(str)
    filtered = filtered[text.apply(lambda row: keyword in " ".join(row).lower(), axis=1)]

st.subheader("历史记录")
st.caption(f"当前筛选结果：{len(filtered)} 条。")
display_columns = [
    "run_label",
    "run_kind",
    "status",
    "validity_status",
    "metrics_reliable",
    "legacy_unverified",
    "strategy",
    "start_date",
    "end_date",
    "updated_at",
    "parent_experiment_id",
    "baseline_run_id",
    "error",
]
st.dataframe(
    localize_frame(filtered[display_columns]), width="stretch", hide_index=True
)
st.download_button(
    "下载回测记录 CSV",
    dataframe_to_csv_bytes(filtered),
    "backtest_run_library.csv",
    "text/csv; charset=utf-8",
)

successful_records = {
    record.run_id: record
    for record in records
    if record.status == RunStatus.SUCCESS and record.run_id in set(filtered["run_id"])
}
if successful_records:
    st.subheader("打开单次结果")
    detail_id = st.selectbox(
        "选择回测",
        list(successful_records),
        format_func=lambda run_id: format_run_label(
            successful_records[run_id], strategy_names
        ),
        key="run_library_detail",
    )
    if st.button("进入单次回测复盘", type="primary"):
        st.session_state["selected_run"] = detail_id
        st.switch_page("home.py")

st.divider()
st.header("结果对比")
if len(successful_records) < 2:
    st.info("当前筛选结果中至少需要两次成功回测才能比较。")
else:
    selected_ids = st.multiselect(
        "选择2～5次回测",
        list(successful_records),
        default=list(successful_records)[:2],
        format_func=lambda run_id: format_run_label(
            successful_records[run_id], strategy_names
        ),
        max_selections=5,
    )
    if len(selected_ids) < 2:
        st.warning("请至少选择两次回测。")
    else:
        comparison = service.run_store.comparison_frame(selected_ids)
        comparison_display = comparison_display_frame(
            comparison, metadata_by_name, strategy_names
        )
        st.dataframe(
            localize_frame(comparison_display), width="stretch", hide_index=True
        )
        nav = service.run_store.normalized_nav(selected_ids)
        if not nav.empty:
            st.subheader("标准化净值（起点=1）")
            labels = {
                run_id: format_run_label(successful_records[run_id], strategy_names)
                for run_id in selected_ids
            }
            nav_display = nav.rename(columns={"trade_date": "交易日期", **labels})
            st.line_chart(nav_display.set_index("交易日期"))
        st.download_button(
            "下载对比结果 CSV",
            dataframe_to_csv_bytes(comparison),
            "backtest_comparison.csv",
            "text/csv; charset=utf-8",
        )
