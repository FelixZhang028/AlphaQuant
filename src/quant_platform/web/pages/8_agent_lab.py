"""智能体分析台：对单只股票运行 LLM 多智能体研究流水线并展示中间产物。

支持：选择数据来源（行情 + 新闻）、专家先验知识、分析后与 AI 对话交锋（人为介入）。
"""

from __future__ import annotations

import datetime as dt

import streamlit as st

from quant_platform.agents_bridge import AgentRunner
from quant_platform.agents_bridge.llm_settings import (
    PROVIDER_CATALOG,
    LLMSettingsStore,
)
from quant_platform.agents_bridge.prior_knowledge import PriorKnowledgeStore
from quant_platform.agents_bridge.proxy_settings import (
    DEFAULT_PROXY_ADDRESS,
    ProxySettingsStore,
)
from quant_platform.agents_bridge.sources import NEWS_SOURCES, STOCK_SOURCES
from quant_platform.application.universe_service import normalize_a_share_symbol
from quant_platform.core.config import load_yaml, require_mapping
from quant_platform.core.exceptions import ConfigurationError
from quant_platform.data.repositories.parquet_repository import (
    ParquetMarketDataRepository,
)
from quant_platform.web.agent_trace import LiveTrace, inject_trace_css, render_replay
from quant_platform.web.theme import inject_global_css
from trading_agents.data.names import CN_NAME_OVERRIDES
from trading_agents.orchestrator.events import EventBus

inject_global_css()
inject_trace_css()

_STATUS_LABELS = {"approved": "批准", "rejected": "拒绝", "conditional": "有条件批准"}
_ACTION_LABELS = {"buy": "买入", "sell": "卖出", "hold": "持有"}


@st.cache_data(ttl=300)
def _load_security_names(repository_path: str) -> dict[str, str]:
    """从证券主数据 parquet 读 {symbol: name} 映射；读失败返回空表。"""
    try:
        table = ParquetMarketDataRepository(repository_path).read_table("security_master")
    except Exception:  # noqa: BLE001 - 缺表/损坏时降级为无名称
        return {}
    if table is None or table.empty or "symbol" not in table.columns:
        return {}
    name_col = table["name"] if "name" in table.columns else ""
    names: dict[str, str] = {}
    for symbol, name in zip(table["symbol"], name_col, strict=False):
        if symbol:
            names[str(symbol)] = str(name) if name else ""
    return names


def _resolve_symbol_name(symbol: str, repository_path: str) -> str | None:
    """按证券主数据 → CN_NAME_OVERRIDES 的顺序查名称；查不到返回 None。"""
    names = _load_security_names(repository_path)
    name = names.get(symbol) or names.get(symbol.split(".")[0])
    if name:
        return name
    return CN_NAME_OVERRIDES.get(symbol.split(".")[0])


def _enum_text(value: object) -> str:
    """枚举取 value，其余转字符串，便于映射中文标签。"""
    return str(getattr(value, "value", value))


def _battle_context(state, decision) -> str:
    """把分析结果压成一段供"与 AI 交锋"引用的上下文。"""
    lines = [
        f"标的: {decision.ticker}",
        f"分析日期: {decision.trade_date}",
        "最终决策: "
        f"{_enum_text(decision.status)} / {_enum_text(decision.final_action)} / "
        f"仓位 {float(decision.final_position_pct):.1%}",
    ]
    if decision.rationale_chain:
        lines.append("理由链: " + "；".join(str(item) for item in decision.rationale_chain))
    if decision.rejection_reason:
        lines.append(f"拒绝原因: {decision.rejection_reason}")
    if state is not None:
        if state.reports:
            for dimension, report in state.reports.items():
                lines.append(f"[{dimension}] 评分{float(report.score):+.2f}：{report.summary}")
        if state.debate is not None:
            if state.debate.bull_summary:
                lines.append(f"多方总结: {state.debate.bull_summary}")
            if state.debate.bear_summary:
                lines.append(f"空方总结: {state.debate.bear_summary}")
        if state.proposal is not None and state.proposal.rationale:
            lines.append(f"提案理由: {state.proposal.rationale}")
    return "\n".join(lines)


st.title("AI研究员")
st.caption("AI 提供分析，你维护的先验知识负责约束边界。")
st.info("本页面仅供研究，不构成投资建议；Trader 提案中的止损价不进入平台回测执行层。")

config_path = "configs/app.yaml"  # 正式版固定配置路径，不再提供侧栏修改入口
try:
    app_config = load_yaml(config_path)
    repository_path = require_mapping(app_config, "data")["repository"]
    repository = ParquetMarketDataRepository(repository_path)
except Exception as exc:
    st.error(f"无法加载数据仓库配置：{exc}")
    st.stop()

store = LLMSettingsStore()
prior_store = PriorKnowledgeStore()
proxy_store = ProxySettingsStore()
proxy_settings = proxy_store.load()

provider = store.get_default_provider()
spec = PROVIDER_CATALOG[provider]
resolved = store.resolve(provider)
key_status = (
    "已配置"
    if resolved["api_key"]
    else ("无需" if not spec.requires_key else "未配置")
)
with st.container(border=True):
    st.markdown(f"**当前模型：{spec.display_name} / {resolved['model'] or '—'}**")
    st.caption(f"API Key：{key_status}。模型和凭证统一在“设置”中管理。")
    st.page_link("pages/14_settings.py", label="研究设置", icon=":material/settings:")

entries = prior_store.list()
with st.container(border=True):
    st.markdown(f"**本次使用的先验知识：{len(entries)} 条**")
    st.caption("运行分析时会注入知识库中的全部条目；新增、检索和删除统一在知识库管理。")
    st.page_link(
        "pages/12_prior_knowledge.py",
        label="管理先验知识",
        icon=":material/library_books:",
    )

st.subheader("研究对象与数据来源")
stock_source = st.selectbox(
    "股票行情来源",
    list(STOCK_SOURCES),
    format_func=lambda key: STOCK_SOURCES[key],
    help="本地行情离线稳定；AkShare / 同花顺 / 东方财富 / yfinance 需联网。",
)
news_all = st.checkbox(
    "全选所有新闻来源",
    value=False,
    help="全选会依次抓取多个新闻源，耗时明显增加。",
)
if news_all:
    selected_news = tuple(NEWS_SOURCES)
    st.warning("已全选所有新闻来源：抓取与清洗耗时将明显增加。")
else:
    selected_news = tuple(
        st.multiselect(
            "新闻来源（可多选）",
            list(NEWS_SOURCES),
            format_func=lambda key: NEWS_SOURCES[key],
            help="新闻是增强输入；抓取失败自动降级为空，不影响行情分析。",
        )
    )
    if len(selected_news) >= 2:
        st.warning(f"已选择 {len(selected_news)} 个新闻来源，耗时将增加。")

proxy_enabled = bool(proxy_settings["enabled"])
proxy_address = str(proxy_settings["address"])

if stock_source == "yfinance" and proxy_enabled:
    st.caption(f"yfinance 将使用设置中的代理：{proxy_address or DEFAULT_PROXY_ADDRESS}")
elif stock_source == "yfinance":
    st.caption("yfinance 代理当前关闭；可在“设置 → 网络与存储”中调整。")

symbol_input = st.text_input("股票代码", "600519", key="agent_lab_symbol").strip()
symbol = symbol_input
if symbol_input:
    try:
        normalized = normalize_a_share_symbol(symbol_input)
    except ConfigurationError:
        st.caption(f"未按 A 股规则识别，将按原样使用：{symbol_input}")
    else:
        symbol = normalized
        name = _resolve_symbol_name(normalized, repository_path)
        if name:
            st.caption(f"已识别：{normalized} ｜ {name}")
        else:
            st.caption(
                f"已识别：{normalized} ｜ 名称未知"
                "（可先在数据管理页更新证券主数据）"
            )

with st.form("agent_lab_form"):
    left, right = st.columns(2)
    with left:
        trade_date = st.date_input("分析日期", dt.date.today())
        lookback_days = st.number_input(
            "回看天数", min_value=20, max_value=250, value=60, step=10
        )
    with right:
        debate_rounds = st.slider("辩论轮数", min_value=0, max_value=4, value=1)
        use_cache = st.checkbox(
            "使用缓存",
            value=True,
            help="命中磁盘缓存时直接展示缓存决策，不重复调用 LLM。取消勾选可实时查看完整分析过程。",
        )
        human_intervention = st.checkbox(
            "人为介入（分析后与 AI 对话交锋）",
            value=False,
            help="勾选后，分析完成可与 AI 就结论对话，提出你的观点或质疑。",
        )

    submitted = st.form_submit_button("运行分析", type="primary")

if submitted:
    if not symbol:
        st.error("请输入股票代码。")
        st.stop()
    if spec.requires_key and not resolved["api_key"]:
        st.error(
            f"{spec.display_name} 未配置 API Key。请前往“设置 → AI 模型”填写，"
            "或设置环境变量后重试。"
        )
        st.stop()
    if provider == "custom" and not resolved["base_url"]:
        st.error("自定义端点需要填写 Base URL。请前往“设置 → AI 模型”填写。")
        st.stop()
    try:
        history = repository.get_daily_bars(symbols=[symbol], end_date=trade_date)
        history = (
            history.sort_values("trade_date").tail(int(lookback_days)).reset_index(drop=True)
        )
    except Exception as exc:
        st.error(f"读取行情数据失败：{exc}")
        st.stop()
    if stock_source == "local" and history.empty:
        st.error(f"{symbol} 在 {trade_date} 及之前没有可用行情数据，请先在数据管理页更新行情。")
        st.stop()
    runner = AgentRunner(
        llm_provider=provider,
        debate_rounds=int(debate_rounds),
        use_cache=use_cache,
        base_url=resolved["base_url"] or None,
        model=resolved["model"] or None,
        api_key=resolved["api_key"] or None,
        prior_knowledge=prior_store.render(),
        stock_source=stock_source,
        news_sources=selected_news,
        proxy_enabled=proxy_enabled,
        proxy_address=proxy_address or DEFAULT_PROXY_ADDRESS,
    )
    state = None
    trace_log: list = []
    try:
        if use_cache:
            with st.spinner("正在读取缓存或运行流水线（勾选缓存时不展示过程）……"):
                decision = runner.decide(symbol, trade_date, history)
        else:
            st.subheader("分析过程")
            trace = LiveTrace()
            bus = EventBus()
            bus.subscribe(trace.on_node)
            state = runner.decide_full(
                symbol, trade_date, history, event_bus=bus, reporter=trace.on_agent
            )
            decision = state.decision
            trace_log = trace.trace_log
    except Exception as exc:
        st.error(f"智能体分析运行失败：{exc}")
        st.stop()
    if decision is None:
        st.error("流水线未产出决策。")
        st.stop()
    st.session_state["battle_history"] = []
    st.session_state["agent_lab_run"] = {
        "decision": decision,
        "state": state,
        "runner": runner,
        "human_intervention": human_intervention,
        "battle_context": _battle_context(state, decision),
        "trace_log": trace_log,
    }

run = st.session_state.get("agent_lab_run")
if run is None:
    st.stop()

decision = run["decision"]
state = run["state"]
runner = run["runner"]
human_intervention = run["human_intervention"]
battle_context = run["battle_context"]

# rerun 后重绘分析过程（终态 stepper + 过程卡片）
trace_log = run.get("trace_log") or []
if trace_log:
    with st.expander("分析过程回放", expanded=True):
        render_replay(trace_log)

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
else:
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
                "建议动作",
                _ACTION_LABELS.get(_enum_text(proposal.action), _enum_text(proposal.action)),
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

# 人为介入：与 AI 对话交锋
if human_intervention:
    st.divider()
    st.subheader("与 AI 对话交锋")
    st.caption("提出你的观点或质疑，AI 会带着完整分析上下文回应；可来回交锋，也可选择相信 AI。")
    if "battle_history" not in st.session_state:
        st.session_state["battle_history"] = []
    for role, text in st.session_state["battle_history"]:
        with st.chat_message(role):
            st.write(text)
    user_message = st.chat_input("输入你的观点 / 质疑 AI 的结论……")
    if user_message:
        st.session_state["battle_history"].append(("user", user_message))
        with st.spinner("AI 正在回应……"):
            try:
                reply = runner.battle(battle_context, user_message)
            except Exception as exc:  # noqa: BLE001 - 交锋失败降级提示
                reply = f"（AI 回应失败：{exc}）"
        st.session_state["battle_history"].append(("assistant", reply))
        st.rerun()
