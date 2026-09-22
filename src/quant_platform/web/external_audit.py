"""Minimal external-material entry point for the credibility audit page."""

import hashlib
from pathlib import Path

import streamlit as st

from quant_platform.core.config import load_app_config
from quant_platform.forensics.checks import (
    ORDER,
    check_trades,
    load_evidence,
    markdown_report,
    verdict,
)
from quant_platform.forensics.parsing import (
    LABELS,
    detect_columns,
    header,
    parse_trades,
    read_material,
)

TEMPLATE = (
    "日期,股票代码,买卖方向,数量（股）,成交价（未复权）\n2024-03-01,000001.SZ,买入,1000,10.50\n"
)


def render_external_audit():
    st.caption("上传成交明细或从 Excel 复制粘贴，检查上市时间、停牌、价格和成交占比。")
    mode = st.radio("导入方式", ["粘贴表格", "上传 CSV"], horizontal=True)
    if mode == "粘贴表格":
        content = st.text_area(
            "粘贴成交记录（含表头）", height=150, key="external_trade_text", placeholder=TEMPLATE
        )
    else:
        upload = st.file_uploader("成交明细 CSV", type=["csv"], key="external_trade_file")
        content = upload.getvalue() if upload else b""
    st.download_button(
        "下载示例模板", TEMPLATE.encode("utf-8-sig"), file_name="成交记录模板.csv", mime="text/csv"
    )
    if not content:
        st.info("只需一份成交明细；净值、截图、委托单和策略描述暂不支持。")
        return
    fingerprint = hashlib.sha256(
        content if isinstance(content, bytes) else content.encode()
    ).hexdigest()
    try:
        frame = read_material(content)
    except ValueError as exc:
        st.error(str(exc))
        return
    mapping = detect_columns(frame)
    missing = [field for field in LABELS if field not in mapping]
    with st.expander("识别结果与预览", expanded=bool(missing)):
        st.dataframe(frame.head(10), hide_index=False, width="stretch")
        st.caption(f"共 {len(frame)} 条；下方报告行号含表头。预览前10条。")
        for field in LABELS:
            if field in missing:
                selected = st.selectbox(
                    f"哪一列是{LABELS[field]}？",
                    [None, *frame.columns],
                    format_func=lambda value: value or "请选择",
                    key=f"map_{fingerprint}_{field}",
                )
                if selected:
                    mapping[field] = selected
            else:
                st.caption(f"{LABELS[field]} ← {mapping[field]}")
    if len(mapping) != 5:
        st.info("请先补充未识别字段。只有净值或持仓列表时，无法完成成交检查。")
        return
    quantity_header = header(mapping["quantity"])
    inferred_unit = "股" if "股" in quantity_header else ("手" if "手" in quantity_header else None)
    unit = inferred_unit or st.selectbox("数量单位是什么？", ["请选择", "股", "手"])
    price_header = header(mapping["price"])
    inferred_raw = "未复权" in price_header
    basis = (
        "未复权"
        if inferred_raw
        else st.selectbox("价格口径是什么？", ["请选择", "未复权", "复权或不确定"])
    )
    if unit == "请选择" or basis == "请选择":
        st.info("确认数量和价格口径后即可检查。")
        return
    st.caption(f"数量按{unit}转换；价格口径：{basis}。本次仅适用于普通上市股票竞价成交。")
    if basis != "未复权":
        st.info("仍可检查时间线和数量；成交价格将标为证据不足。")
    try:
        parsed = parse_trades(frame, mapping, unit)
    except ValueError as exc:
        st.error(str(exc))
        return
    if not parsed.errors.empty:
        st.error("请先修正以下问题，不会静默丢弃错误行。")
        st.dataframe(parsed.errors, hide_index=True)
        return
    if parsed.trades.duplicated(["date", "symbol", "side", "quantity", "price"]).any():
        if not st.checkbox("存在相同成交记录：我已核实它们是独立成交，并非重复导出"):
            st.warning("重复记录会放大成交占比，请先核实。")
            return
    key = repr((fingerprint, mapping, unit, basis))
    if st.button("检查", type="primary", key="check_external"):
        try:
            with st.spinner("正在核对本地数据……"):
                config = load_app_config("configs/app.yaml")
                root = Path(config["data"]["repository"]).resolve()
                master, bars = load_evidence(root, parsed.trades)
                findings = check_trades(parsed.trades, master, bars, basis == "未复权")
                st.session_state["external_audit_result"] = (key, findings)
        except Exception:
            st.session_state.pop("external_audit_result", None)
            st.error("本地数据暂时无法读取，请检查数据目录或等待更新结束后重试。")
    saved = st.session_state.get("external_audit_result")
    if saved is None or saved[0] != key:
        return
    findings = saved[1]
    st.subheader(verdict(findings))
    st.caption("结论仅针对本次材料及可核查项目，不证明策略有效或原始材料真实。")
    cols = st.columns(4)
    for col, label in zip(cols, ORDER, strict=True):
        col.metric(label, int((findings["结论"] == label).sum()))
    covered = len(parsed.trades) - findings[findings["结论"].eq("证据不足")]["表格行"].nunique()
    st.caption(f"证据齐备的成交记录：{covered}/{len(parsed.trades)}；上方数字按核查项统计。")
    selection = st.multiselect("查看结论", ORDER, default=ORDER, key="external_findings_filter")
    st.dataframe(findings[findings["结论"].isin(selection)], hide_index=True, width="stretch")
    st.download_button(
        "下载检查报告", markdown_report(findings), file_name="外部成交检查.md", mime="text/markdown"
    )
