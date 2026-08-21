"""智能体分析台：对单只股票运行 LLM 多智能体研究流水线并展示中间产物。"""

from __future__ import annotations

import datetime as dt

import streamlit as st

from quant_platform.agents_bridge import AgentRunner
from quant_platform.core.config import load_yaml, require_mapping
from quant_platform.data.repositories.parquet_repository import (
    ParquetMarketDataRepository,
)

# provider → (显示图标, 说明)
_LLM_PROVIDERS: dict[str, tuple[str, str]] = {
    "mock": ("🧪", "mock 离线确定，零成本，结果可复现"),
    "kimi": ("🌙", "Kimi 开放平台（Moonshot）"),
    "openai": ("🅾️", "OpenAI GPT 系列"),
    "deepseek": ("🔮", "DeepSeek"),
    "qwen": ("🌀", "通义千问（阿里云）"),
    "glm": ("📐", "智谱 GLM"),
    "ollama": ("🖥️", "Ollama 本地模型"),
    "custom": ("⚙️", "自定义 OpenAI 兼容端点"),
}
_STATUS_LABELS = {"approved": "批准", "rejected": "拒绝", "conditional": "有条件批准"}
_ACTION_LABELS = {"buy": "买入", "sell": "卖出", "hold": "持有"}


def _enum_text(value: object) -> str:
    """枚举取 value，其余转字符串，便于映射中文标签。"""
    return str(getattr(value, "value", value))


st.title("智能体分析台")
st.caption("单票 LLM 多智能体研究：分析师团队 → 多空辩论 → 交易员提案 → 风控 → 组合经理审批。")
st.info("本页面仅供研究，不构成投资建议；Trader 提案中的止损价不进入平台回测执行层。")

config_path = st.sidebar.text_input(
    "应用配置", "configs/app.yaml", key="agent_lab_config_path"
)
try:
    app_config = load_yaml(config_path)
    repository_path = require_mapping(app_config, "data")["repository"]
    repository = ParquetMarketDataRepository(repository_path)
except Exception as exc:
    st.error(f"无法加载数据仓库配置：{exc}")
    st.stop()

with st.form("agent_lab_form"):
    left, right = st.columns(2)
    with left:
        symbol = st.text_input("股票代码", "600519.SH").strip()
        trade_date = st.date_input("分析日期", dt.date.today())
        lookback_days = st.number_input(
            "回看天数", min_value=20, max_value=250, value=60, step=10
        )
    with right:
        llm_provider = st.selectbox(
            "LLM Provider",
            list(_LLM_PROVIDERS),
            format_func=lambda p: f"{_LLM_PROVIDERS[p][0]} {p} — {_LLM_PROVIDERS[p][1]}",
            help="mock 离线确定，其他 provider 需配置对应 API Key 环境变量。",
        )
        debate_rounds = st.slider("辩论轮数", min_value=0, max_value=4, value=1)
        use_cache = st.checkbox(
            "使用缓存", value=True, help="命中磁盘缓存时直接展示缓存决策，不重复调用 LLM。"
        )

    # 自定义模型扩展输入
    custom_base_url = ""
    custom_model = ""
    if llm_provider == "custom":
        st.divider()
        st.caption("自定义模型配置")
        custom_left, custom_right = st.columns(2)
        with custom_left:
            custom_base_url = st.text_input(
                "Base URL",
                value="https://api.openai.com/v1",
                help="OpenAI 兼容的聊天补全端点，需以 /v1 结尾。",
            )
        with custom_right:
            custom_model = st.text_input(
                "模型名称",
                value="gpt-4o-mini",
                help="该端点支持的模型名。",
            )
        st.info(
            "自定义端点通过环境变量 `OPENAI_COMPAT_API_KEY` 读取 API Key；"
            "如需使用其他环境变量名，请在 trading_agents/config.py 中修改。"
        )

    submitted = st.form_submit_button("运行分析", type="primary")

if not submitted:
    st.stop()

if not symbol:
    st.error("请输入股票代码。")
    st.stop()

try:
    history = repository.get_daily_bars(symbols=[symbol], end_date=trade_date)
    history = history.sort_values("trade_date").tail(int(lookback_days)).reset_index(drop=True)
except Exception as exc:
    st.error(f"读取行情数据失败：{exc}")
    st.stop()

if history.empty:
    st.error(f"{symbol} 在 {trade_date} 及之前没有可用行情数据，请先在数据管理页更新行情。")
    st.stop()

runner = AgentRunner(
    llm_provider=llm_provider,
    debate_rounds=int(debate_rounds),
    use_cache=use_cache,
    base_url=custom_base_url or None,
    model=custom_model or None,
)
state = None
try:
    with st.spinner("正在运行多智能体流水线……"):
        if use_cache:
            # 优先查缓存；未命中时 decide() 内部会跑完整流水线并写缓存
            decision = runner.decide(symbol, trade_date, history)
        else:
            state = runner.decide_full(symbol, trade_date, history)
            decision = state.decision
except Exception as exc:
    st.error(f"智能体分析运行失败：{exc}")
    st.stop()

if decision is None:
    st.error("流水线未产出决策。")
    st.stop()

# 顶部 PM 决策卡片
st.subheader("组合经理决策")
status, action, position = st.columns(3)
status.metric(
    "审批状态", _STATUS_LABELS.get(_enum_text(decision.status), _enum_text(decision.status))
)
action.metric(
    "最终动作",
    _ACTION_LABELS.get(_enum_text(decision.final_action), _enum_text(decision.final_action)),
)
position.metric("目标仓位", f"{float(decision.final_position_pct):.1%}")
if decision.rejection_reason:
    st.warning(f"拒绝原因：{decision.rejection_reason}")
if decision.conditions:
    st.write("通过条件：" + "；".join(str(item) for item in decision.conditions))
if decision.rationale_chain:
    with st.expander("理由链", expanded=True):
        for item in decision.rationale_chain:
            st.write(f"- {item}")

if state is None:
    st.caption('本次结果来自决策缓存，仅展示最终决策；取消勾选"使用缓存"可查看完整中间产物。')
    st.stop()

# 分析师报告
if state.reports:
    with st.expander("分析师报告", expanded=False):
        for dimension, report in state.reports.items():
            st.markdown(
                f"**{dimension}** ｜ 评分 {float(report.score):+.2f} ｜ "
                f"置信度 {float(report.confidence):.2f}"
            )
            st.write(report.summary)
            for finding in report.key_findings:
                st.write(f"- {finding}")
            if report.red_flags:
                st.write("风险提示：" + "；".join(str(flag) for flag in report.red_flags))
            st.divider()

# 多空辩论
if state.debate is not None:
    with st.expander("多空辩论全文", expanded=False):
        for turn in state.debate.turns:
            stance = "多方" if turn.stance == "bull" else "空方"
            st.markdown(f"**第 {turn.round} 轮 · {stance}**")
            st.write(turn.argument)
            if turn.response_to_opponent:
                st.caption(f"回应对方：{turn.response_to_opponent}")
        if state.debate.bull_summary:
            st.write(f"多方总结：{state.debate.bull_summary}")
        if state.debate.bear_summary:
            st.write(f"空方总结：{state.debate.bear_summary}")

# Trader 提案
if state.proposal is not None:
    proposal = state.proposal
    with st.expander("Trader 提案", expanded=False):
        st.metric(
            "建议动作", _ACTION_LABELS.get(_enum_text(proposal.action), _enum_text(proposal.action))
        )
        columns = st.columns(4)
        columns[0].metric("建议仓位", f"{float(proposal.position_pct):.1%}")
        columns[1].metric("置信度", f"{float(proposal.confidence):.2f}")
        columns[2].metric(
            "止损价", f"{proposal.stop_loss:.2f}" if proposal.stop_loss is not None else "—"
        )
        columns[3].metric(
            "目标价",
            f"{proposal.target_price:.2f}" if proposal.target_price is not None else "—",
        )
        st.caption("止损价与目标价仅供研究参考，不进入平台回测执行层。")
        st.write(f"持有周期：{proposal.holding_horizon}")
        st.write(f"提案理由：{proposal.rationale}")

# 风控评估
if state.risk is not None:
    risk = state.risk
    with st.expander("风控评估", expanded=False):
        columns = st.columns(3)
        columns[0].metric("是否否决", "是" if risk.veto else "否")
        columns[1].metric("波动水平", risk.volatility_level)
        columns[2].metric("估计最大回撤", f"{float(risk.max_drawdown_est):.1%}")
        if risk.veto_reason:
            st.warning(f"否决原因：{risk.veto_reason}")
        if risk.conditions:
            st.write("通过条件：" + "；".join(str(item) for item in risk.conditions))
        if risk.commentary:
            st.write(risk.commentary)

# 模拟成交（T+1 语义，仅供核对）
if state.fill is not None:
    with st.expander("模拟成交", expanded=False):
        st.write(
            f"动作 {_enum_text(state.fill.action)}，数量 {state.fill.quantity:.0f} 股，"
            f"成交价 {state.fill.price:.2f}（基准 {state.fill.reference_price:.2f}），"
            f"费用 {state.fill.commission:.2f}，交收日 {state.fill.settlement_date}"
        )

if state.error:
    st.warning(f"流水线记录了非致命错误：{state.error}")
