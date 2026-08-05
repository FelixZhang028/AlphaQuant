"""Streamlit interface for persistent portfolio risk limits."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from quant_platform.application.backtest_service import BacktestService
from quant_platform.core.config import load_yaml
from quant_platform.risk.config import RiskLimits, load_risk_limits, save_risk_limits
from quant_platform.web.localization import localize_frame

st.title("风险管理")
st.caption("所有策略共用的组合级风控参数；修改后会应用到新运行的回测和模拟账户。")

config_path = st.sidebar.text_input("风险管理配置", "configs/app.yaml", key="risk_app_config_path")
try:
    app = load_yaml(config_path)
    risk_reference = app.get("risk", {})
    risk_path = Path(str(risk_reference.get("config", "configs/risk.yaml")))
    limits = load_risk_limits(risk_path)
except Exception as exc:
    st.error(f"无法加载风控配置：{exc}")
    st.stop()

with st.form("risk_limits_form"):
    enabled = st.checkbox("启用风控", value=limits.enabled)
    left, right = st.columns(2)
    with left:
        max_total_weight = st.number_input(
            "最大总仓位", 0.0, 1.0, limits.max_total_weight, 0.05, format="%.2f"
        )
        max_single_weight = st.number_input(
            "单只股票最大权重", 0.0, 1.0, limits.max_single_weight, 0.05, format="%.2f"
        )
        max_positions = st.number_input(
            "最大持股数量", min_value=1, value=limits.max_positions, step=1
        )
    with right:
        minimum_cash_ratio = st.number_input(
            "最低现金比例", 0.0, 1.0, limits.minimum_cash_ratio, 0.05, format="%.2f"
        )
        max_drawdown = st.number_input(
            "最大回撤停止线", 0.0, 1.0, limits.max_drawdown, 0.05, format="%.2f"
        )
        st.info("回撤达到停止线后，系统停止生成新的调仓订单，但不会自动清仓。")
    saved = st.form_submit_button("保存风控配置", type="primary")

if saved:
    try:
        updated = RiskLimits(
            enabled=enabled,
            max_total_weight=float(max_total_weight),
            max_single_weight=float(max_single_weight),
            max_positions=int(max_positions),
            minimum_cash_ratio=float(minimum_cash_ratio),
            max_drawdown=float(max_drawdown),
        )
        save_risk_limits(risk_path, updated)
        st.success(f"已保存到 {risk_path}")
    except Exception as exc:
        st.error(f"风控配置无效：{exc}")

st.divider()
st.header("最近风控记录")
try:
    service = BacktestService(config_path)
    frames: list[pd.DataFrame] = []
    for record in service.run_store.list_records(successful_only=True)[:10]:
        path = record.path / "risk_events.parquet"
        if path.exists():
            frame = pd.read_parquet(path)
            frame.insert(0, "run_id", record.run_id)
            frames.append(frame)
    if not frames:
        st.info("还没有新版风控记录，请先运行一次回测。")
    else:
        events = pd.concat(frames, ignore_index=True).sort_values("trade_date", ascending=False)
        rejected = events[events["decision"].eq("REJECT")]
        checks, rejections = st.columns(2)
        checks.metric("最近检查次数", f"{len(events):,}")
        rejections.metric("拒绝次数", f"{len(rejected):,}")
        st.dataframe(localize_frame(events.head(500)), width="stretch", hide_index=True)
except Exception as exc:
    st.warning(f"暂时无法读取风控记录：{exc}")
