"""命令行实时 TUI（基于 rich Live），布局对标 TradingAgents 开源界面。

三栏布局：
- 左上 **Progress**：Team / Agent / Status 表格，分析过程中实时刷新
  （pending / in_progress / completed / error）。
- 右上 **Messages & Tools**：Time / Type / Content 滚动日志，
  Type 为 tool（agent 启动、数据节点）或 reasoning（agent 产出摘要）。
- 下方 **Current Report**：最新完成的 Agent 产出全文，以 ``[agent]:`` 开头，
  按 Markdown 渲染（有序/无序列表，段落间空行）。

Agent 级状态来自 ``PipelineContext.agent_reporter`` 回调（编排层可选订阅点）。
仅依赖 rich，不引入 questionary。

非交互用法（测试/脚本）：:func:`run_tui_noninteractive` 直接渲染一轮。
"""

from __future__ import annotations

import datetime as dt
import sys as _sys

from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from trading_agents.cli import DISCLAIMER
from trading_agents.config import TradingConfig
from trading_agents.orchestrator import (
    EventBus,
    NodeEvent,
    PipelineContext,
    PipelineState,
    run_pipeline,
)
from trading_agents.schemas import (
    AnalystReport,
    DebateTurn,
    Decision,
    RiskAssessment,
    TradeProposal,
)

_PROVIDERS = ["mock", "kimi", "openai", "deepseek", "qwen", "glm", "ollama"]
_DATA_SOURCES = [
    "stub", "yfinance", "eastmoney", "akshare", "tonghuashun", "auto",
]

# 各 provider 可选模型（TUI 单选列表；kimi 模型以 platform.kimi.com/docs/models 为准）
PROVIDER_MODELS: dict[str, list[str]] = {
    "mock": ["mock-llm"],
    "kimi": ["kimi-k3", "kimi-k2.7-code", "kimi-k2.6", "kimi-k2.5"],
    "openai": ["gpt-4o-mini", "gpt-4o"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "qwen": ["qwen-plus", "qwen-max"],
    "glm": ["glm-4-plus", "glm-4-air"],
    "ollama": ["qwen2.5:7b", "llama3.1:8b"],
}

# 可选分析师维度（TUI 多选）
ANALYST_CHOICES: list[tuple[str, str]] = [
    ("fundamental", "Fundamental Analyst 基本面"),
    ("sentiment", "Sentiment Analyst 情绪"),
    ("news", "News Analyst 新闻/宏观"),
    ("technical", "Technical Analyst 技术面"),
]


# ------------------------------------------------------------ 交互选择 ----

def _tty_select(
    console: Console, title: str, options: list[str], multi: bool
) -> list[int]:
    """键盘交互选择：↑/↓ 移动，空格切换，a 全选（multi），Enter 确认。

    返回选中下标列表。仅 Windows msvcrt 实现；其他环境返回 None 走降级。
    """
    if not _sys.stdin.isatty():
        return []
    try:
        import msvcrt
    except ImportError:
        return []

    cursor, selected = 0, set()
    radio_on, radio_off = ("◉", "○") if _UTF8_OK else ("(*)", "( )")
    box_on, box_off = ("☑", "☐") if _UTF8_OK else ("[x]", "[ ]")

    def draw() -> None:
        lines = [title]
        for i, opt in enumerate(options):
            if multi:
                mark = box_on if i in selected else box_off
            else:
                mark = radio_on if i == cursor else radio_off
            ptr = "❯" if i == cursor else " "
            lines.append(f"{ptr} {mark} {opt}")
        hint = "↑/↓ 移动 · 空格切换 · a 全选 · Enter 确认" if multi else "↑/↓ 移动 · Enter 确认"
        lines.append(f"[dim]{hint}[/dim]")
        console.print("\n".join(lines))
        return len(lines)

    n = draw()
    while True:
        key = msvcrt.getwch()
        if key in ("\x00", "\xe0"):  # 功能键前缀
            key = msvcrt.getwch()
            if key == "H":
                cursor = (cursor - 1) % len(options)
            elif key == "P":
                cursor = (cursor + 1) % len(options)
        elif key == " " and multi:
            selected.symmetric_difference_update({cursor})
        elif key.lower() == "a" and multi:
            selected = set() if len(selected) == len(options) else set(range(len(options)))
        elif key == "\r":
            if multi:
                if selected:
                    break
            else:
                selected = {cursor}
                break
        else:
            continue
        # 重绘：光标移回块首
        console.file.write(f"\x1b[{n}A")
        console.file.flush()
        n = draw()
    if not multi:
        selected = {cursor}
    return sorted(selected)


def select_options(
    console: Console, title: str, options: list[str], multi: bool = False
) -> list[str]:
    """选项列表选择（⚪ 单选 / 多选）；非 TTY 环境降级为编号输入。"""
    picked = _tty_select(console, title, options, multi)
    if not picked:
        # 降级：编号输入
        console.print(title)
        for i, opt in enumerate(options, 1):
            console.print(f"  {i}. {opt}")
        if multi:
            raw = Prompt.ask("编号（逗号分隔，a=全选）", default="a", console=console)
            picked = list(range(len(options))) if raw.strip().lower() == "a" else [
                int(x.strip()) - 1 for x in raw.split(",") if x.strip().isdigit()
            ]
        else:
            raw = Prompt.ask("编号", default="1", console=console)
            picked = [int(raw) - 1] if raw.strip().isdigit() else [0]
    return [options[i] for i in picked if 0 <= i < len(options)]

# (Team, Agent 显示名, agent key)——Progress 表格的固定行序
AGENT_ROSTER: list[tuple[str, str, str]] = [
    ("Analyst Team", "Fundamental Analyst", "fundamental"),
    ("Analyst Team", "Sentiment Analyst", "sentiment"),
    ("Analyst Team", "News Analyst", "news"),
    ("Analyst Team", "Technical Analyst", "technical"),
    ("Research Team", "Bull Researcher", "bull"),
    ("Research Team", "Bear Researcher", "bear"),
    ("Trading Team", "Trader", "trader"),
    ("Risk Management", "Risk Team", "risk"),
    ("Portfolio Management", "Portfolio Manager", "pm"),
]

# 控制台编码不含 Unicode 符号时（如 Windows GBK）降级为纯文本标记
_UTF8_OK = "utf" in ((_sys.stdout.encoding or "").lower())
_MARKS = {"completed": "✓", "in_progress": "▶", "error": "✗", "skipped": "–", "pending": "·"}
_STATUS_STYLE = {
    "completed": "green",
    "in_progress": "bold yellow",
    "error": "bold red",
    "skipped": "dim strike",
    "pending": "dim",
}

# agent / 节点启动时在 Messages 面板显示的「在做什么」
_DOING = {
    "fundamental": "分析财务与估值…",
    "sentiment": "聚合情绪读数…",
    "news": "解读新闻与宏观…",
    "technical": "计算技术指标…",
    "bull": "构建看多论点…",
    "bear": "构建看空论点…",
    "trader": "汇总形成交易提案…",
    "risk": "评估波动/流动性/集中度…",
    "pm": "最终审批裁决…",
    "resolve_identity": "解析标的身份",
    "fetch_data": "拉取数据快照",
    "execute": "模拟交易所撮合",
    "record_memory": "沉淀决策记忆",
}


# ------------------------------------------------------------ 内容构建 ----

def _report_markdown(agent: str, payload: object) -> str:
    """把 agent 产出渲染为 Markdown（``[agent]:`` 开头，列表分点）。"""
    if isinstance(payload, AnalystReport):
        lines = [
            f"[{agent}]: {payload.summary}",
            "",
            f"- **score**: {payload.score:+.2f}   **confidence**: {payload.confidence:.2f}",
            "",
        ]
        if payload.key_findings:
            lines.append("**key findings**:")
            lines.append("")
            for i, f in enumerate(payload.key_findings, 1):
                src = f"（来源: {f.source}）" if f.source else ""
                lines.append(f"{i}. {f.claim} — {f.evidence}{src}")
            lines.append("")
        if payload.red_flags:
            lines.append("**red flags**:")
            lines.append("")
            for flag in payload.red_flags:
                lines.append(f"- {flag}")
        return "\n".join(lines)
    if isinstance(payload, DebateTurn):
        lines = [
            f"[{agent}] 第{payload.round}轮: {payload.argument}",
            "",
        ]
        if payload.response_to_opponent:
            lines += [f"- **回应对方**: {payload.response_to_opponent}", ""]
        if payload.evidence:
            lines.append("**证据**:")
            lines.append("")
            for e in payload.evidence:
                lines.append(f"- {e}")
        return "\n".join(lines)
    if isinstance(payload, TradeProposal):
        return "\n".join([
            f"[trader]: {payload.rationale}",
            "",
            f"1. **action**: {payload.action.value}   **position**: {payload.position_pct:.0%}",
            f"2. **entry**: {payload.entry_price}   **stop_loss**: {payload.stop_loss}   "
            f"**target**: {payload.target_price}",
            f"3. **horizon**: {payload.holding_horizon}   **confidence**: {payload.confidence:.2f}",
        ])
    if isinstance(payload, RiskAssessment):
        lines = [
            f"[risk]: 回撤估计 {payload.max_drawdown_est:.0%}，"
            f"波动 {payload.volatility_level}，veto={payload.veto}",
            "",
        ]
        if payload.veto and payload.veto_reason:
            lines += [f"- **否决原因**: {payload.veto_reason}", ""]
        if payload.conditions:
            lines.append("**通过条件**:")
            lines.append("")
            for c in payload.conditions:
                lines.append(f"- {c}")
        return "\n".join(lines)
    if isinstance(payload, Decision):
        lines = [
            f"[pm]: {payload.status.value} → {payload.final_action.value} "
            f"{payload.final_position_pct:.0%}",
            "",
        ]
        if payload.rejection_reason:
            lines += [f"- **驳回原因**: {payload.rejection_reason}", ""]
        if payload.rationale_chain:
            lines.append("**理由链**:")
            lines.append("")
            for link in payload.rationale_chain:
                lines.append(f"- {link}")
        return "\n".join(lines)
    return f"[{agent}]: {payload}"


# ------------------------------------------------------------ 渲染 ----

def render_progress(agent_status: dict[str, str]) -> Panel:
    """左上 Progress：Team / Agent / Status 表格。"""
    table = Table(expand=True, show_edge=False, pad_edge=False)
    table.add_column("Team", style="cyan", no_wrap=True)
    table.add_column("Agent", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    prev_team = ""
    for team, agent_name, key in AGENT_ROSTER:
        status = agent_status.get(key, "pending")
        # UTF-8 终端带符号标记；GBK 终端只显示状态文字避免截断
        label = f"{_MARKS.get(status, '')} {status}" if _UTF8_OK else status
        style = _STATUS_STYLE.get(status, "dim")
        table.add_row(
            team if team != prev_team else "",
            agent_name,
            Text(label, style=style),
        )
        prev_team = team
    return Panel(table, title="Progress", border_style="cyan")


def render_messages(rows: list[tuple[str, str, str]], max_rows: int = 9) -> Panel:
    """右上 Messages & Tools：Time / Type / Content，只保留最近几行工具调用。"""
    table = Table(expand=True, show_edge=False, pad_edge=False)
    table.add_column("Time", style="dim", no_wrap=True)
    table.add_column("Type", no_wrap=True)
    table.add_column("Content", overflow="fold")
    for t, typ, content in rows[-max_rows:]:
        style = {"tool": "magenta", "error": "bold red"}.get(typ, "")
        table.add_row(t, Text(typ, style=style), content)
    return Panel(table, title="Messages & Tools", border_style="blue")


def render_current_report(title: str, markdown: str) -> Panel:
    """下方 Current Report：最新 agent 产出的 Markdown 渲染。"""
    body = Markdown(markdown) if markdown else Text("（等待 Agent 产出…）", style="dim")
    return Panel(body, title=title, border_style="green")


# ------------------------------------------------------------ TUI 主体 ----

class TradingTUI:
    """事件驱动的实时界面：订阅节点事件 + agent 级 reporter，即刷新 Live。

    Messages 面板只记录「调用了什么、在做什么」（工具/函数级）；
    分析产出的全文按完成顺序累积进 Current Report（Markdown 渲染）。
    """

    def __init__(self, console: Console | None = None, max_msg_rows: int = 60) -> None:
        self.console = console or Console()
        self.agent_status: dict[str, str] = {}
        self.msg_rows: list[tuple[str, str, str]] = []
        self.max_msg_rows = max_msg_rows
        self.report_sections: list[str] = []
        self._live: Live | None = None

    # ---------------- 事件入口 ----------------
    def on_agent(self, agent: str, status: str, payload: object = None) -> None:
        """agent 级进度回调（PipelineContext.agent_reporter）。"""
        self.agent_status[agent] = status
        now = dt.datetime.now().strftime("%H:%M:%S")
        if status == "in_progress":
            self._log(now, "tool", f"run {agent} · {_DOING.get(agent, '')}")
        elif status == "completed":
            self.report_sections.append(_report_markdown(agent, payload))
            self.report_sections = self.report_sections[-12:]
        elif status == "error":
            self._log(now, "error", f"[{agent}] {payload}")
        self._refresh()

    def on_event(self, event: NodeEvent, state: PipelineState) -> None:
        """EventBus 节点事件：只记录工具调用与错误。"""
        now = dt.datetime.now().strftime("%H:%M:%S")
        if event.kind == "started" and event.node in _DOING:
            self._log(now, "tool", f"{event.node} · {_DOING[event.node]}")
        elif event.kind == "finished":
            if event.status == "error":
                self._log(now, "error", f"{event.node}: {event.error}")
                for key, st in self.agent_status.items():
                    if st == "in_progress":
                        self.agent_status[key] = "error"
            elif event.node == "fetch_data" and state is not None and state.snapshot:
                s = state.snapshot
                self._log(
                    now,
                    "tool",
                    f"快照就绪 as_of={s.as_of_date} close={s.last_close} bars={len(s.bars)}",
                )
            elif event.node == "execute":
                filled = state and state.fill
                self._log(now, "tool", "成交回报已生成" if filled else "无成交（驳回或 hold）")
        self._refresh()

    # ---------------- 内部 ----------------
    def _log(self, t: str, typ: str, content: str) -> None:
        self.msg_rows.append((t, typ, content))
        self.msg_rows = self.msg_rows[-self.max_msg_rows:]

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self.render())

    def render(self) -> Group:
        grid = Table.grid(expand=True)
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)
        grid.add_row(
            render_progress(self.agent_status),
            render_messages(self.msg_rows),
        )
        body_md = "\n\n---\n\n".join(self.report_sections)
        bottom = render_current_report("Current Report", body_md)
        return Group(grid, bottom)

    def run_pipeline_live(
        self,
        symbol: str,
        trade_date: dt.date,
        ctx: PipelineContext,
        resume: bool = True,
    ) -> PipelineState:
        """在 Live 布局中执行流水线，事件实时刷新。"""
        bus = EventBus()
        bus.subscribe(self.on_event)
        ctx.agent_reporter = self.on_agent
        with Live(self.render(), console=self.console, refresh_per_second=8) as live:
            self._live = live
            try:
                state = run_pipeline(symbol, trade_date, ctx, resume=resume, event_bus=bus)
            finally:
                self._live = None
        return state


# ------------------------------------------------------------ 交互入口 ----

def prompt_inputs(console: Console) -> tuple[str, dt.date, str, str, str, list[str], int, bool]:
    """交互式收集运行参数（单选 ⚪ / 多选 ☑ 列表 + 键盘操作）。"""
    ticker = Prompt.ask("标的代码", default="AAPL", console=console).strip().upper()
    while True:
        raw = Prompt.ask("分析日期 (YYYY-MM-DD)", default=str(dt.date.today()), console=console)
        try:
            trade_date = dt.date.fromisoformat(raw)
            break
        except ValueError:
            console.print("[red]日期格式错误，请重新输入[/red]")
    provider = select_options(console, "[bold]LLM provider（单选）[/bold]", _PROVIDERS)[0]
    model = select_options(
        console, f"[bold]{provider} 模型（单选）[/bold]", PROVIDER_MODELS[provider]
    )[0]
    data = select_options(console, "[bold]数据源（单选）[/bold]", _DATA_SOURCES)[0]
    analyst_labels = [label for _, label in ANALYST_CHOICES]
    picked = select_options(console, "[bold]分析师团队（多选）[/bold]", analyst_labels, multi=True)
    dims = [k for (k, label) in ANALYST_CHOICES if label in picked] or [
        k for k, _ in ANALYST_CHOICES
    ]
    rounds = int(Prompt.ask("辩论轮数", default="2", console=console))
    resume = not Confirm.ask("强制重跑（忽略 checkpoint）？", default=False, console=console)
    return ticker, trade_date, provider, model, data, dims, rounds, resume


def print_final(console: Console, state: PipelineState) -> None:
    """结束后打印最终 Decision + Fill 摘要与免责声明。"""
    console.rule("最终结果")
    if state.identity is not None:
        idn = state.identity
        console.print(f"标的: [bold]{idn.name}[/bold] ({idn.symbol})  "
                      f"行业: {idn.industry or '-'}  货币: {idn.currency}")
    if state.snapshot is not None and state.snapshot.market_cap:
        console.print(f"总市值: {state.snapshot.market_cap:,.0f} "
                      f"{state.identity.currency if state.identity else ''}  "
                      f"最新收盘: {state.snapshot.last_close}")
    d = state.decision
    if d is not None:
        console.print(
            f"审批: [bold]{d.status.value}[/bold]  动作: {d.final_action.value}  "
            f"仓位: {d.final_position_pct:.1%}"
        )
        if d.rejection_reason:
            console.print(f"驳回原因: {d.rejection_reason}")
        for link in d.rationale_chain:
            console.print(f"  理由链: {link}")
    if state.fill is not None:
        f = state.fill
        console.print(
            f"成交: {f.action.value} {f.quantity} @ {f.price} "
            f"(滑点 {f.slippage}, 手续费 {f.commission}, 交收 {f.settlement_date})"
        )
    else:
        console.print("成交: 无（被驳回或 hold）")
    console.print(f"产物: {state.artifacts}")
    console.print(f"[dim]{DISCLAIMER}[/dim]")


def run_tui() -> int:
    """TUI 主入口：交互收集参数 → Live 实时运行 → 最终摘要。"""
    # Windows GBK 控制台无法编码 Markdown 的 • 等符号，降级替换而非崩溃
    for stream in (_sys.stdout, _sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass
    console = Console()
    console.print(f"[yellow]{DISCLAIMER}[/yellow]")
    ticker, trade_date, provider, model, data, dims, rounds, resume = prompt_inputs(console)

    config = TradingConfig.load(provider=provider)
    config.debate_rounds = rounds
    config.llm.deep_think_model = model
    config.llm.quick_think_model = model
    config.analyst_dims = dims
    from trading_agents.cli import build_context  # 复用 CLI 的装配逻辑

    try:
        ctx = build_context(config, data)
    except (KeyError, RuntimeError) as exc:
        console.print(f"[red]配置错误：{exc}[/red]")
        return 2

    tui = TradingTUI(console)
    # 未选中的分析师维度直接标记 skipped，Progress 面板状态完整
    for key, _label in ANALYST_CHOICES:
        if key not in dims:
            tui.agent_status[key] = "skipped"
    try:
        state = tui.run_pipeline_live(ticker, trade_date, ctx, resume=resume)
    except RuntimeError as exc:
        console.print(f"[red]流水线失败：{exc}[/red]")
        return 1
    print_final(console, state)
    if not Confirm.ask("再次分析？", default=False, console=console):
        return 0
    return run_tui()


def run_tui_noninteractive(console: Console | None = None) -> None:
    """非交互验证：固定参数跑一遍渲染流程（供测试/脚本调用）。"""
    console = console or Console(record=True, width=140)
    config = TradingConfig.load(provider="mock")
    from trading_agents.cli import build_context

    ctx = build_context(config, "stub")
    tui = TradingTUI(console)
    state = tui.run_pipeline_live("AAPL", dt.date(2024, 6, 3), ctx, resume=False)
    print_final(console, state)


if __name__ == "__main__":
    raise SystemExit(run_tui())
