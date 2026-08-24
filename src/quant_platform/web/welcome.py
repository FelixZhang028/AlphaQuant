"""落地主页：DeepSeek Harness 着陆页风格，由本地配置与数据状态驱动。

布局：顶部品牌条（LOGO+名字 / 中英文切换）→ hero（深蓝丝绸光带面板：介绍 +
悬浮终端卡 + 胶囊功能键 + 向下滚动指示）→ 新手上路（独占一屏）→ 模块直达 →
平台状态 → 最近运行。
"""

from __future__ import annotations

import streamlit as st

from quant_platform.application.backtest_service import BacktestService
from quant_platform.application.paper_service import PaperTradingService
from quant_platform.application.readiness_service import (
    PlatformReadinessService,
    ReadinessStatus,
)
from quant_platform.application.strategy_studio_service import StrategyStudioService
from quant_platform.backtest.run_store import RunStatus
from quant_platform.web.guide import StepState, build_guide_steps
from quant_platform.web.run_comparison import RUN_KIND_LABELS
from quant_platform.web.run_labels import format_run_label
from quant_platform.web.theme import (
    github_link_html,
    render_check_row,
    render_hero,
    render_module_card,
    render_run_row,
    render_section,
    topbar_html,
)

_STATE_TO_DOT = {
    ReadinessStatus.READY: "ok",
    ReadinessStatus.WARNING: "warn",
    ReadinessStatus.ACTION: "err",
}

_RUN_TO_DOT = {
    RunStatus.SUCCESS: "ok",
    RunStatus.RUNNING: "warn",
    RunStatus.CREATED: "idle",
    RunStatus.FAILED: "err",
}

# ── 中英文案（主页范围内） ─────────────────────────────────────────
_TEXT: dict[str, dict[str, object]] = {
    "zh": {
        "eyebrow": "AlphaQuant 量化工作台",
        "title": "数据到决策，",
        "accent": "一站完成。",
        "subtitle": "从股票池、行情数据到策略回测与 LLM 智能体研究，一站式完成。"
        "系统会自动检查本地配置与数据，并告诉你下一步该做什么。",
        "badge_local": "本地优先 · 数据私有",
        "ready_pill": "● 已具备回测条件",
        "warn_pill": "● 首次准备尚未完成",
        "cta_backtest": "进入回测",
        "cta_agent": "智能体分析台",
        "cta_data": "数据管理",
        "cta_pool": "股票池管理",
        "term_comment": "# 分析师团队 → 多空辩论 → 风控 → PM 审批",
        "term_decision": "决策完成：买入 · 目标仓位 60.0%",
        "term_backtest": "回测完成：年化 18.2% · 最大回撤 -8.4%",
        "scroll_hint": "向下滚动",
        "sec_guide": "新手上路",
        "sec_guide_hint": "按顺序完成六步，即可从数据走到模拟交易；高级参数在各页面内折叠隐藏",
        "sec_modules": "模块直达",
        "sec_modules_hint": "从任意卡片进入对应工作台",
        "open": "打开",
        "sec_status": "平台状态",
        "sec_status_hint": "本地配置与数据检查结果",
        "status_note": "平台会自动检查本地配置与数据，<br/>"
        "并按下方顺序引导你完成首次准备，<br/>无需手工编辑配置文件。",
        "sec_runs": "最近运行",
        "sec_runs_hint": "最近一次成功或失败的回测记录",
        "no_runs": "暂无回测记录，先从「单次回测与复盘」运行一次吧。",
        "goto_backtest": "去运行一次回测",
        "all_runs": "查看全部记录",
        "trouble_title": "环境检查明细与排障",
        "trouble_body": """
- **股票池为空**：前往「股票池管理」，输入六位股票代码并保存。
- **没有股票行情**：前往「数据管理」，勾选「更新配置股票池行情」。
- **历史天数不足**：把数据更新的开始日期向前调整，再次更新。
- **证券主表缺失**：仍可通过代码添加股票，但按名称搜索前需要更新证券主表。
- **网络更新失败**：检查网络或代理后重试；已经成功的数据不会被删除。
""",
        "ready_footer": "已具备回测条件",
        "not_ready_footer": "数据就绪后可运行",
        "pool_footer_ok": "已配置 {n} 只股票",
        "pool_footer_empty": "尚未添加股票",
        "data_footer": "覆盖 {ok}/{total} 只",
    },
    "en": {
        "eyebrow": "AlphaQuant Workbench",
        "title": "From data to decisions,",
        "accent": "all in one place.",
        "subtitle": "Universe, market data, strategy backtesting and LLM multi-agent "
        "research in one workbench. Local configuration and data are checked "
        "automatically, with guidance for your next step.",
        "badge_local": "Local-first · Private data",
        "ready_pill": "● Ready for backtest",
        "warn_pill": "● Setup incomplete",
        "cta_backtest": "Run Backtest",
        "cta_agent": "Agent Lab",
        "cta_data": "Data Management",
        "cta_pool": "Universe",
        "term_comment": "# analysts → bull/bear debate → risk → PM approval",
        "term_decision": "Decision: BUY · target position 60.0%",
        "term_backtest": "Backtest done: 18.2% ann. · -8.4% max drawdown",
        "scroll_hint": "Scroll down",
        "sec_guide": "Getting Started",
        "sec_guide_hint": "Follow the six steps from data to paper trading",
        "sec_modules": "Modules",
        "sec_modules_hint": "Jump into any workbench",
        "open": "Open",
        "sec_status": "Platform Status",
        "sec_status_hint": "Local configuration & data checks",
        "status_note": "The platform checks local configuration and data automatically,<br/>"
        "and guides you through first-time setup —<br/>no config files to edit.",
        "sec_runs": "Recent Runs",
        "sec_runs_hint": "Latest backtest records, success or failure",
        "no_runs": "No backtest records yet — run one from Backtest & Review.",
        "goto_backtest": "Run a backtest",
        "all_runs": "View all records",
        "trouble_title": "Environment checks & troubleshooting",
        "trouble_body": """
- **Empty universe**: go to Universe and save six-digit symbols.
- **No market data**: go to Data Management and enable universe bar updates.
- **Insufficient history**: move the update start date earlier and update again.
- **Missing security master**: symbols still work; update the master table for name search.
- **Network failures**: check your network or proxy; completed data is never deleted.
""",
        "ready_footer": "Ready for backtest",
        "not_ready_footer": "Available once data is ready",
        "pool_footer_ok": "{n} symbols configured",
        "pool_footer_empty": "No symbols yet",
        "data_footer": "Coverage {ok}/{total}",
    },
}

_MODULES: dict[str, list[tuple[str, str, str, str, str]]] = {
    # icon, title, desc, page, footer 模板键或原文
    "zh": [
        ("hub", "策略创作中心",
         "模板、积木、自然语言、Python 四种方式创建策略，统一注册与回测。",
         "pages/0_strategy_hub.py", "统一入口"),
        ("candlestick_chart", "单次回测与复盘",
         "选择策略并运行一次完整回测，查看收益、回撤与可信度审计。", "home.py", ""),
        ("widgets", "零代码策略工作台",
         "以声明式参数与规则搭建策略，自动生成参数表单，无需编写代码。",
         "pages/7_strategy_studio.py", "零代码 · 参数化"),
        ("code", "自定义策略（Python）",
         "在网页中编写或上传 Python 策略，自动解析参数并生成表单。",
         "pages/8_custom_strategy.py", "Python 进阶"),
        ("psychology", "智能体分析台",
         "LLM 多智能体协作完成行情解读、因子研究与交易分析。",
         "pages/8_agent_lab.py", "多智能体研究"),
        ("science", "因子研究室",
         "内置量价因子的 IC、分层收益与稳定性评估，支持多因子合成选股。",
         "pages/9_factor_lab.py", "IC · 分层 · 合成"),
        ("chat", "自然语言建策略",
         "用一句话描述策略，大模型转成结构化规则，确认后保存。",
         "pages/10_nl_strategy.py", "DeepSeek / Kimi / Ollama"),
        ("database", "数据管理",
         "下载证券主表、股票日线与基准行情，检查覆盖率和数据质量。",
         "pages/1_data_management.py", ""),
        ("tune", "参数优化与稳健性验证",
         "网格 / 随机搜索参数组合，并用样本外数据验证策略稳健性。",
         "pages/2_research.py", "搜索 + 样本外验证"),
        ("history", "回测记录库",
         "统一管理单次回测、参数优化与样本外验证结果，支持比较。",
         "pages/6_run_library.py", "历史记录 · 对比"),
        ("shield", "风险管理",
         "事件化风控检查与决策记录，为模拟交易提供前置拦截。",
         "pages/3_risk_management.py", "事件检查 · 决策"),
        ("account_balance", "模拟交易",
         "以真实行情节奏模拟下单，追踪账户净值与交易明细。",
         "pages/4_paper_trading.py", "paper trading"),
        ("list_alt", "股票池管理",
         "添加股票、配置回测区间与最小历史天数，管理研究标的。",
         "pages/5_universe_management.py", ""),
    ],
    "en": [
        ("hub", "Strategy Hub",
         "Templates, blocks, natural language or Python — one registration flow.",
         "pages/0_strategy_hub.py", "Unified entry"),
        ("candlestick_chart", "Backtest & Review",
         "Run a full backtest with a strategy; inspect returns, drawdowns and audits.",
         "home.py", ""),
        ("widgets", "No-Code Strategy Studio",
         "Build strategies declaratively with auto-generated parameter forms.",
         "pages/7_strategy_studio.py", "No-code · Parametric"),
        ("code", "Custom Strategy (Python)",
         "Write or upload Python strategies in the browser with parsed parameters.",
         "pages/8_custom_strategy.py", "Advanced Python"),
        ("psychology", "Agent Lab",
         "LLM multi-agent research: market reading, factor study, trade analysis.",
         "pages/8_agent_lab.py", "Multi-agent research"),
        ("science", "Factor Lab",
         "IC, quantile returns and stability for built-in factors; composite scoring.",
         "pages/9_factor_lab.py", "IC · Groups · Composite"),
        ("chat", "NL Strategy Builder",
         "Describe a strategy in one sentence; the LLM drafts structured rules.",
         "pages/10_nl_strategy.py", "DeepSeek / Kimi / Ollama"),
        ("database", "Data Management",
         "Fetch security master, daily bars and benchmarks; check coverage & quality.",
         "pages/1_data_management.py", ""),
        ("tune", "Optimization & Robustness",
         "Grid / random parameter search with out-of-sample validation.",
         "pages/2_research.py", "Search + OOS validation"),
        ("history", "Run Library",
         "Manage backtests, optimizations and OOS results; compare runs.",
         "pages/6_run_library.py", "History · Compare"),
        ("shield", "Risk Management",
         "Event-based risk checks and decisions guarding paper trading.",
         "pages/3_risk_management.py", "Event checks · Decisions"),
        ("account_balance", "Paper Trading",
         "Simulated orders at real market pace; track equity and fills.",
         "pages/4_paper_trading.py", "paper trading"),
        ("list_alt", "Universe",
         "Add symbols, configure backtest range and minimum history.",
         "pages/5_universe_management.py", ""),
    ],
}


def _lang() -> str:
    return st.session_state.get("aq_lang", "zh")


def _t(key: str) -> str:
    return str(_TEXT[_lang()][key])


def _check_state(report, item: str) -> str:
    """把某个检查项映射成 Harness 状态圆点。"""
    for check in report.checks:
        if check.item == item:
            return _STATE_TO_DOT.get(check.status, "idle")
    return "idle"


def _render_stickybar(report) -> None:
    """顶部悬浮导航条：网页名 / 语言切换 / GitHub（带图标）。

    页面顶端为透明状态（贴在网页顶部）；向下滚动时背景变为毛玻璃，并
    在「中文/EN」切换右侧浮现一个 GitHub 按钮。布局为：左（LOGO+名字+状态）
    右（语言切换 + GitHub）。
    """
    ready_pill = (
        f'<span class="aq-pill aq-pill-ok">{_t("ready_pill")}</span>'
        if report.ready_for_backtest
        else f'<span class="aq-pill aq-pill-warn">{_t("warn_pill")}</span>'
    )
    with st.container(key="aq_stickybar"):
        brand_col, lang_col, github_col = st.columns([1, 1, 1])
        with brand_col:
            st.markdown(
                topbar_html("AlphaQuant", pills=(ready_pill,)),
                unsafe_allow_html=True,
            )
        with lang_col:
            choice = st.segmented_control(
                "Language / 语言",
                ["中文", "EN"],
                default="中文" if _lang() == "zh" else "EN",
                label_visibility="collapsed",
            )
        with github_col:
            st.markdown(
                github_link_html("https://github.com/FelixZhang028/AlphaQuant"),
                unsafe_allow_html=True,
            )
    if choice:
        lang = "zh" if choice == "中文" else "en"
        if lang != _lang():
            st.session_state["aq_lang"] = lang
            st.rerun()


def _render_hero(report) -> None:
    """深蓝丝绸 hero：介绍 + 终端卡 + 胶囊功能键（品牌条由顶部悬浮导航条负责）。"""
    render_hero(
        _t("title"),
        _t("subtitle"),
        accent=_t("accent"),
        badge=_t("badge_local"),
        eyebrow=_t("eyebrow"),
        terminal=(
            '<span class="aq-term-prompt">$</span> alphaquant agent analyze 600519',
            f'<span class="aq-term-dim">{_t("term_comment")}</span>',
            f'<span class="aq-term-ok">✓</span> {_t("term_decision")}',
            '<span class="aq-term-prompt">$</span> alphaquant backtest --strategy momentum',
            f'<span class="aq-term-ok">✓</span> {_t("term_backtest")}',
        ),
        scroll_hint=_t("scroll_hint"),
    )
    with st.container(key="aq_hero_ctas"):
        columns = st.columns([1, 1, 1, 1, 4])
        ctas = [
            ("cta_backtest", "home.py", report.ready_for_backtest),
            ("cta_agent", "pages/8_agent_lab.py", True),
            ("cta_data", "pages/1_data_management.py", True),
            ("cta_pool", "pages/5_universe_management.py", True),
        ]
        for column, (key, page, enabled) in zip(columns, ctas, strict=False):
            with column:
                if st.button(_t(key), key=f"welcome_cta_{page}", disabled=not enabled):
                    st.switch_page(page)


_GUIDE_ICONS = {StepState.DONE: "✅", StepState.CURRENT: "👉", StepState.TODO: "⬜"}


def _render_guide(report, config_path: str) -> None:
    """新手引导分步向导（反馈第 1 条）：六步流程 + 当前建议步骤高亮。"""

    has_strategies = False
    has_runs = False
    has_paper = False
    try:
        backtests = BacktestService(config_path)
        has_strategies = bool(StrategyStudioService(backtests).store.list())
        has_runs = bool(backtests.run_store.list_records())
        has_paper = bool(PaperTradingService(backtests).list_accounts())
    except Exception:  # noqa: BLE001 - 引导信息缺失不应影响主页
        pass

    steps = build_guide_steps(
        configured_symbols=report.configured_symbols,
        symbols_with_sufficient_history=report.symbols_with_sufficient_history,
        has_strategies=has_strategies,
        has_backtest_runs=has_runs,
        has_paper_accounts=has_paper,
    )
    render_section(_t("sec_guide"), _t("sec_guide_hint"))
    columns = st.columns(len(steps))
    for column, step in zip(columns, steps, strict=True):
        with column:
            icon = _GUIDE_ICONS[step.state]
            # key 供 CSS 做逐级延迟的滚动渐入，请勿改名（theme.py 有对应选择器）
            with st.container(border=True, key=f"aq_guide_step_{step.key}"):
                st.markdown(f"{icon} **{step.title}**")
                st.caption(step.hint)
                if st.button(
                    step.action,
                    key=f"guide_step_{step.key}",
                    use_container_width=True,
                    type=(
                        "primary" if step.state == StepState.CURRENT else "secondary"
                    ),
                ):
                    st.switch_page(step.page)


def _render_modules(report) -> None:
    """渲染模块直达卡片网格。"""
    render_section(_t("sec_modules"), _t("sec_modules_hint"))
    pool_ok = report.configured_symbols > 0
    footers = {
        "home.py": (
            ("ok" if report.ready_for_backtest else "warn"),
            _t("ready_footer") if report.ready_for_backtest else _t("not_ready_footer"),
        ),
        "pages/1_data_management.py": (
            _check_state(report, "股票行情"),
            _t("data_footer")
            .replace("{ok}", str(report.symbols_with_sufficient_history))
            .replace("{total}", str(report.configured_symbols)),
        ),
        "pages/5_universe_management.py": (
            "ok" if pool_ok else "err",
            _t("pool_footer_ok").replace("{n}", str(report.configured_symbols))
            if pool_ok
            else _t("pool_footer_empty"),
        ),
    }
    modules = _MODULES[_lang()]
    for offset in range(0, len(modules), 4):
        row = modules[offset : offset + 4]
        columns = st.columns(4)
        for column, (icon, title, desc, page, footer) in zip(
            columns, row, strict=False
        ):
            state, footer_text = footers.get(page, ("idle", footer))
            with column:
                render_module_card(
                    icon, title, desc, state, footer_text, delay_ms=offset * 60
                )
                if st.button(
                    _t("open"), key=f"welcome_module_{page}", use_container_width=True
                ):
                    st.switch_page(page)


def _render_status(report) -> None:
    """渲染平台状态：就绪度 + 环境检查行。"""
    render_section(_t("sec_status"), _t("sec_status_hint"))
    summary_col, rows_col = st.columns([1, 3], gap="large")
    with summary_col:
        pill_class = "aq-pill-ok" if report.ready_for_backtest else "aq-pill-warn"
        pill_text = _t("ready_pill") if report.ready_for_backtest else _t("warn_pill")
        st.markdown(
            f'<span class="aq-pill {pill_class}" style="height:32px;font-size:13px;">'
            f"{pill_text}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div style="margin-top:1rem;color:#81858c;font-size:0.85rem;'
            f'line-height:1.7;">{_t("status_note")}</div>',
            unsafe_allow_html=True,
        )
    with rows_col:
        for check in report.checks:
            render_check_row(
                check.item,
                _STATE_TO_DOT.get(check.status, "idle"),
                check.detail,
                check.destination or "",
            )


def _render_recent_runs(config_path: str) -> None:
    """渲染最近运行记录。"""
    render_section(_t("sec_runs"), _t("sec_runs_hint"))
    try:
        service = BacktestService(config_path)
        records = service.run_store.list_records()[:5]
        metadata = {item.plugin_name: item for item in service.available_strategies()}
        names = {name: item.display_name for name, item in metadata.items()}
    except Exception:
        records = []
        names = {}
    if not records:
        st.markdown(
            '<div style="color:#81858c;font-size:0.88rem;padding:0.4rem 0.2rem;">'
            f'{_t("no_runs")}</div>',
            unsafe_allow_html=True,
        )
        if st.button(_t("goto_backtest"), key="welcome_goto_backtest"):
            st.switch_page("home.py")
        return
    for record in records:
        label = format_run_label(record, names)
        meta = record.created_at[:16].replace("T", " ")
        render_run_row(
            label,
            _RUN_TO_DOT.get(record.status, "idle"),
            meta,
            RUN_KIND_LABELS.get(record.run_kind, record.run_kind),
        )
    if st.button(_t("all_runs"), key="welcome_all_runs"):
        st.switch_page("pages/6_run_library.py")


def main() -> None:
    config_path = st.sidebar.text_input(
        "应用配置", "configs/app.yaml", key="welcome_config_path"
    )
    report = PlatformReadinessService(config_path).inspect()

    _render_stickybar(report)

    with st.container(key="aq_hero_wrap"):
        _render_hero(report)

    with st.container(key="aq_sec_guide"):
        _render_guide(report, config_path)
    with st.container(key="aq_sec_modules"):
        _render_modules(report)
    with st.container(key="aq_sec_status"):
        _render_status(report)
    with st.container(key="aq_sec_runs"):
        _render_recent_runs(config_path)

    with st.container(key="aq_sec_detail"):
        st.divider()
        with st.expander(_t("trouble_title")):
            st.dataframe(report.to_frame(), width="stretch", hide_index=True)
            st.markdown(_t("trouble_body"))


main()
