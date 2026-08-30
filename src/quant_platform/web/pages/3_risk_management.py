"""Streamlit interface for persistent portfolio risk limits."""

from __future__ import annotations

from quant_platform.web.theme import inject_global_css

inject_global_css()


from pathlib import Path

import pandas as pd
import streamlit as st

from quant_platform.application.backtest_service import BacktestService
from quant_platform.core.config import load_yaml
from quant_platform.risk.config import RiskLimits, load_risk_limits, save_risk_limits
from quant_platform.web.localization import localize_frame

st.title("风险管理")
st.caption("所有策略共用的组合级风控参数；修改后会应用到新运行的回测和模拟账户。")

config_path = "configs/app.yaml"  # 正式版固定配置路径，不再提供侧栏修改入口
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
        daily_position_limits = st.checkbox(
            "每日检查实际持仓并自动纠偏",
            value=limits.daily_position_limits,
            help="持仓上涨导致单股、总仓位或持股数量超限时，下一交易日自动减仓。",
        )
    with right:
        minimum_cash_ratio = st.number_input(
            "最低现金比例", 0.0, 1.0, limits.minimum_cash_ratio, 0.05, format="%.2f"
        )
        max_drawdown = st.number_input(
            "最大回撤停止线", 0.0, 1.0, limits.max_drawdown, 0.05, format="%.2f"
        )
        action_options = ["stop_new", "reduce", "liquidate"]
        action_labels = {
            "stop_new": "停止新开仓",
            "reduce": "自动降低仓位",
            "liquidate": "自动清仓",
        }
        drawdown_action = st.selectbox(
            "达到回撤线后的处理",
            action_options,
            index=action_options.index(limits.drawdown_action),
            format_func=lambda value: action_labels[value],
        )
        drawdown_target_weight = st.number_input(
            "降仓后的最大总仓位",
            0.0,
            1.0,
            limits.drawdown_target_weight,
            0.05,
            format="%.2f",
            disabled=drawdown_action != "reduce",
        )
        st.info("风控在每日收盘后检查实际持仓，纠偏订单在下一交易日开盘执行。")
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
            daily_position_limits=bool(daily_position_limits),
            drawdown_action=str(drawdown_action),
            drawdown_target_weight=float(drawdown_target_weight),
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
        adjusted = events[events["decision"].eq("ADJUST")]
        checks, adjustments, rejections = st.columns(3)
        checks.metric("最近检查次数", f"{len(events):,}")
        adjustments.metric("自动调整次数", f"{len(adjusted):,}")
        rejections.metric("拒绝次数", f"{len(rejected):,}")
        st.dataframe(localize_frame(events.head(500)), width="stretch", hide_index=True)
except Exception as exc:
    st.warning(f"暂时无法读取风控记录：{exc}")