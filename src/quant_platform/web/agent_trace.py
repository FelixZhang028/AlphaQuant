"""智能体分析台：LLM 分析过程实时可视化（stepper + 过程卡片 + 回放）。

- ``inject_trace_css()``：注入本模块全部样式（纯 CSS 动画，支持 reduced-motion
  与亮色模式兜底）。
- ``LiveTrace``：订阅 EventBus 节点事件与 AgentReporter 回调，在 Streamlit
  容器中实时渲染流水线进度与中间产物；渲染异常不影响流水线。
- ``render_replay()``：页面 rerun 后从 ``trace_log`` 重绘终态过程区。
"""

from __future__ import annotations

import html
from typing import Any

import streamlit as st

from trading_agents.schemas.models import (
    AnalystReport,
    DebateTurn,
    Decision,
    RiskAssessment,
    TradeProposal,
)

# 流水线节点 → 中文标签（顺序即 stepper 展示顺序）
NODE_LABELS: dict[str, str] = {
    "resolve_identity": "标的识别",
    "fetch_data": "数据获取",
    "analyst_team": "分析师团队",
    "debate": "多空辩论",
    "trader_proposal": "交易员提案",
    "risk_review": "风控审核",
    "pm_approval": "组合经理审批",
    "execute": "模拟成交",
    "record_memory": "记忆归档",
}
_NODE_ORDER: list[str] = list(NODE_LABELS)

_ACTION_LABELS = {"buy": "买入", "sell": "卖出", "hold": "持有"}
_STATUS_LABELS = {"approved": "批准", "rejected": "拒绝", "conditional": "有条件批准"}
_AGENT_LABELS = {
    "fundamental": "基本面分析师",
    "sentiment": "情绪分析师",
    "news": "新闻分析师",
    "technical": "技术分析师",
    "bull": "多方辩手",
    "bear": "空方辩手",
    "trader": "交易员",
    "risk": "风控团队",
    "pm": "组合经理",
}


def _esc(text: object) -> str:
    return html.escape(str(text))


def _enum_text(value: object) -> str:
    return str(getattr(value, "value", value))


# ------------------------------------------------------------------ CSS ----


def inject_trace_css() -> None:
    """注入分析过程可视化所需的全部页面 CSS（纯 CSS 动画）。"""
    st.markdown(
        """
<style>
/* ---------- 9 步 stepper ---------- */
.aq-stepper {
    display: flex; flex-wrap: wrap; align-items: flex-start;
    gap: 4px 0; margin: 0.25rem 0 0.5rem;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.aq-step {
    display: flex; flex-direction: column; align-items: center;
    width: 11%; min-width: 88px;
}
.aq-step .aq-dot {
    width: 14px; height: 14px; border-radius: 50%;
    border: 2px solid rgba(255,255,255,.18);
    background: transparent; position: relative; z-index: 1;
    display: flex; align-items: center; justify-content: center;
    font-size: 9px; color: #3fb950; line-height: 1;
}
.aq-step .aq-line {
    position: relative; top: -8px; height: 2px; width: 100%;
    background: rgba(255,255,255,.08); z-index: 0;
}
.aq-step .aq-label {
    margin-top: 4px; font-size: 0.72rem; color: #8b949e;
    text-align: center; white-space: nowrap;
}
.aq-step .aq-dur {
    font-size: 0.62rem; color: #6e7681; margin-top: 1px;
    font-variant-numeric: tabular-nums;
}
.aq-step.is-running .aq-dot {
    border-color: #58a6ff;
    animation: aqPulse 1.2s ease-in-out infinite;
}
.aq-step.is-running .aq-label { color: #58a6ff; }
.aq-step.is-done .aq-dot {
    border-color: #3fb950; background: rgba(63,185,80,.15);
}
.aq-step.is-done .aq-dot::after { content: "✓"; font-size: 9px; color: #3fb950; }
.aq-step.is-done .aq-line { background: rgba(63,185,80,.4); }
.aq-step.is-done .aq-label { color: #c9d1d9; }
.aq-step.is-skipped .aq-dot {
    border-color: rgba(255,255,255,.12); background: rgba(255,255,255,.04);
}
.aq-step.is-skipped .aq-label { color: #6e7681; text-decoration: line-through; }
.aq-step.is-error .aq-dot { border-color: #f85149; background: rgba(248,81,73,.15); }
.aq-step.is-error .aq-label { color: #f85149; }

@keyframes aqPulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(88,166,255,.35); }
    50% { box-shadow: 0 0 8px 3px rgba(88,166,255,.5); }
}

/* 底部细进度条 */
.aq-progress {
    height: 2px; background: rgba(255,255,255,.08);
    border-radius: 1px; overflow: hidden; margin-bottom: 0.5rem;
}
.aq-progress > div {
    height: 100%; background: #58a6ff;
    transition: width .6s ease;
}

/* ---------- 过程卡片 ---------- */
.aq-card {
    border: 1px solid rgba(255,255,255,.06);
    border-radius: 4px;
    padding: 0.65rem 0.8rem;
    margin: 0.45rem 0;
    background: rgba(255,255,255,.015);
    animation: aqFadeSlideIn 300ms ease-out both;
    font-size: 0.88rem;
}
.aq-card h5 {
    margin: 0 0 0.3rem; font-size: 0.8rem; color: #8b949e;
    font-weight: 600; letter-spacing: 0.02em;
}
.aq-card .aq-num {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-variant-numeric: tabular-nums;
}
.aq-card ul { margin: 0.2rem 0 0.1rem 1.1rem; padding: 0; }
.aq-card li { margin: 0.1rem 0; }

@keyframes aqFadeSlideIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}

/* 评分条 */
.aq-score-bar {
    height: 6px; border-radius: 3px;
    background: rgba(255,255,255,.08);
    overflow: hidden; margin: 0.3rem 0;
}
.aq-score-bar > div {
    height: 100%;
    background: linear-gradient(90deg, #f85149, #d29922 50%, #3fb950);
    transition: width .6s ease;
}

/* chip */
.aq-chip {
    display: inline-block; padding: 1px 8px; margin: 2px 4px 2px 0;
    border: 1px solid rgba(248,81,73,.4); border-radius: 999px;
    font-size: 0.72rem; color: #f85149;
}

/* 辩论气泡 */
.aq-bubble {
    max-width: 85%; padding: 0.5rem 0.75rem; margin: 0.4rem 0;
    border-radius: 4px; font-size: 0.86rem;
    background: rgba(255,255,255,.02);
    animation: aqFadeSlideIn 300ms ease-out both;
}
.aq-bubble-bull { border-left: 3px solid #d29922; margin-right: auto; }
.aq-bubble-bear { border-right: 3px solid #58a6ff; margin-left: auto; text-align: left; }
.aq-bubble .aq-bubble-head { font-size: 0.74rem; color: #8b949e; margin-bottom: 0.2rem; }
.aq-bubble-bull .aq-bubble-head { color: #d29922; }
.aq-bubble-bear .aq-bubble-head { color: #58a6ff; }

/* 正在思考 */
.aq-thinking {
    color: #8b949e; font-size: 0.82rem; margin: 0.35rem 0;
    white-space: nowrap;
    animation: aqThink 1.4s ease-in-out infinite;
}
@keyframes aqThink {
    0%, 100% { opacity: 0.35; }
    50% { opacity: 1; }
}
/* 思考完成（就地状态切换，非动画） */
.aq-done {
    color: #3fb950; font-size: 0.82rem; margin: 0.35rem 0;
    white-space: nowrap;
}

/* ---------- 可访问性 / 亮色兜底 ---------- */
@media (prefers-reduced-motion: reduce) {
    .aq-step .aq-dot, .aq-card, .aq-bubble, .aq-thinking { animation: none !important; }
    .aq-score-bar > div, .aq-progress > div { transition: none !important; }
}
@media (prefers-color-scheme: light) {
    .aq-card { border-color: rgba(0,0,0,.1); background: rgba(0,0,0,.015); }
    .aq-card h5, .aq-step .aq-label { color: #57606a; }
    .aq-step.is-done .aq-label { color: #24292f; }
    .aq-step .aq-dot { border-color: rgba(0,0,0,.2); }
    .aq-step .aq-line { background: rgba(0,0,0,.08); }
    .aq-bubble { background: rgba(0,0,0,.02); }
    .aq-score-bar { background: rgba(0,0,0,.08); }
    .aq-progress { background: rgba(0,0,0,.08); }
    .aq-thinking { color: #57606a; }
}
</style>
""",
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------- HTML 构建 ----


def _stepper_html(nodes: dict[str, dict[str, Any]]) -> str:
    """根据节点状态字典渲染 stepper + 底部进度条 HTML。"""
    parts: list[str] = ['<div class="aq-stepper">']
    done_count = 0
    for index, name in enumerate(_NODE_ORDER):
        info = nodes.get(name, {})
        status = info.get("status", "pending")
        css = {
            "running": "is-running",
            "ok": "is-done",
            "skipped": "is-skipped",
            "error": "is-error",
        }.get(status, "")
        if status in ("ok", "skipped"):
            done_count += 1
        line = "" if index == 0 else '<div class="aq-line"></div>'
        duration = info.get("duration_ms", 0.0)
        dur_html = ""
        if status == "ok" and duration:
            seconds = duration / 1000.0
            text = (
                f"{seconds:.1f}s"
                if seconds < 60
                else f"{int(seconds // 60)}m{seconds % 60:.0f}s"
            )
            dur_html = f'<div class="aq-dur">{text}</div>'
        parts.append(
            f'<div class="aq-step {css}">{line}<div class="aq-dot"></div>'
            f'<div class="aq-label">{_esc(NODE_LABELS[name])}</div>{dur_html}</div>'
        )
    parts.append("</div>")
    pct = done_count / len(_NODE_ORDER) * 100
    parts.append(f'<div class="aq-progress"><div style="width:{pct:.0f}%"></div></div>')
    return "".join(parts)


def _analyst_card_html(report: AnalystReport, delay_ms: int = 0) -> str:
    score = float(report.score)
    pct = max(0.0, min(1.0, (score + 1.0) / 2.0)) * 100
    chips = "".join(f'<span class="aq-chip">{_esc(flag)}</span>' for flag in report.red_flags)
    findings = "".join(
        f"<li>{_esc(f.claim)} — {_esc(f.evidence)}</li>" for f in report.key_findings
    )
    return (
        f'<div class="aq-card" style="animation-delay:{delay_ms}ms">'
        f"<h5>分析师报告 · {_esc(report.dimension)}</h5>"
        f'<div class="aq-num">评分 {score:+.2f} ｜ 置信度 {float(report.confidence):.2f}</div>'
        f'<div class="aq-score-bar"><div style="width:{pct:.0f}%"></div></div>'
        f"<div>{_esc(report.summary)}</div>"
        + (f"<ul>{findings}</ul>" if findings else "")
        + (f"<div>{chips}</div>" if chips else "")
        + "</div>"
    )


def _debate_bubble_html(turn: DebateTurn) -> str:
    css = "aq-bubble-bull" if turn.stance == "bull" else "aq-bubble-bear"
    stance = "多方" if turn.stance == "bull" else "空方"
    response = (
        f'<div style="margin-top:0.25rem;color:#8b949e;font-size:0.78rem">'
        f"回应对方：{_esc(turn.response_to_opponent)}</div>"
        if turn.response_to_opponent
        else ""
    )
    return (
        f'<div class="aq-bubble {css}">'
        f'<div class="aq-bubble-head">第 {turn.round} 轮 · {stance}</div>'
        f"<div>{_esc(turn.argument)}</div>{response}</div>"
    )


def _proposal_card_html(proposal: TradeProposal) -> str:
    action = _ACTION_LABELS.get(_enum_text(proposal.action), _enum_text(proposal.action))
    stop = f"{proposal.stop_loss:.2f}" if proposal.stop_loss is not None else "—"
    target = f"{proposal.target_price:.2f}" if proposal.target_price is not None else "—"
    return (
        '<div class="aq-card"><h5>交易员提案</h5>'
        f'<div class="aq-num">动作 {action} ｜ 仓位 {float(proposal.position_pct):.1%} ｜ '
        f"止损 {stop} ｜ 目标 {target} ｜ 置信度 {float(proposal.confidence):.2f}</div>"
        f"<div>{_esc(proposal.rationale)}</div></div>"
    )


def _risk_card_html(risk: RiskAssessment) -> str:
    veto = "是" if risk.veto else "否"
    parts = [
        '<div class="aq-card"><h5>风控评估</h5>',
        f'<div class="aq-num">否决 {veto} ｜ 波动 {_esc(risk.volatility_level)} ｜ '
        f"估计最大回撤 {float(risk.max_drawdown_est):.1%}</div>",
    ]
    if risk.veto_reason:
        parts.append(f'<div style="color:#f85149">否决原因：{_esc(risk.veto_reason)}</div>')
    if risk.commentary:
        parts.append(f"<div>{_esc(risk.commentary)}</div>")
    parts.append("</div>")
    return "".join(parts)


def _decision_card_html(decision: Decision) -> str:
    status = _STATUS_LABELS.get(_enum_text(decision.status), _enum_text(decision.status))
    action = _ACTION_LABELS.get(
        _enum_text(decision.final_action), _enum_text(decision.final_action)
    )
    chain = "".join(f"<li>{_esc(item)}</li>" for item in decision.rationale_chain[:4])
    parts = [
        '<div class="aq-card"><h5>组合经理决策</h5>',
        f'<div class="aq-num">{status} ｜ {action} ｜ 仓位 '
        f"{float(decision.final_position_pct):.1%}</div>",
    ]
    if decision.rejection_reason:
        parts.append(
            f'<div style="color:#f85149">驳回原因：{_esc(decision.rejection_reason)}</div>'
        )
    if chain:
        parts.append(f"<ul>{chain}</ul>")
    parts.append("</div>")
    return "".join(parts)


def _payload_card_html(payload: Any) -> str | None:
    """按 payload 类型渲染过程卡片；未知类型返回 None。"""
    if isinstance(payload, AnalystReport):
        return _analyst_card_html(payload)
    if isinstance(payload, DebateTurn):
        return _debate_bubble_html(payload)
    if isinstance(payload, TradeProposal):
        return _proposal_card_html(payload)
    if isinstance(payload, RiskAssessment):
        return _risk_card_html(payload)
    if isinstance(payload, Decision):
        return _decision_card_html(payload)
    return None


# ------------------------------------------------------------- LiveTrace ----


class LiveTrace:
    """运行期实时渲染：节点 stepper + 过程卡片流。

    事件为同线程同步回调：回调内直接更新 st.empty() / 追加到 st.container()。
    渲染异常全部吞掉，绝不影响流水线。
    """

    def __init__(self) -> None:
        self._stepper_slot = st.empty()
        self._body = st.container()
        self.nodes: dict[str, dict[str, Any]] = {}
        self.agents: list[dict[str, Any]] = []
        self.trace_log: list[dict[str, Any]] = []
        self._agent_slots: dict[str, Any] = {}  # agent -> 状态占位，用于就地更新
        self._redraw_stepper()

    # ---------------- 事件入口 ----------------
    def on_node(self, event: Any, state: Any = None) -> None:
        """EventBus 订阅回调：更新节点状态并重绘 stepper。"""
        try:
            node = event.node
            if event.kind == "started":
                self.nodes[node] = {"status": "running"}
            else:
                self.nodes[node] = {
                    "status": event.status or "ok",
                    "duration_ms": float(event.duration_ms or 0.0),
                    "summary": event.summary or "",
                    "error": event.error or "",
                }
            self.trace_log.append(
                {
                    "kind": "node",
                    "node": node,
                    "event": event.kind,
                    "status": event.status or "",
                    "duration_ms": float(event.duration_ms or 0.0),
                    "summary": event.summary or "",
                    "error": event.error or "",
                }
            )
            self._redraw_stepper()
        except Exception:  # noqa: BLE001 - 渲染异常不影响流水线
            pass

    def on_agent(self, agent: str, status: str, payload: Any = None) -> None:
        """AgentReporter 回调：in_progress 显示思考动画，completed 就地切换为完成并渲染卡片。"""
        try:
            label = _AGENT_LABELS.get(agent, agent)
            if status == "in_progress":
                slot = self._agent_slots.get(agent)
                if slot is None:
                    slot = self._body.empty()
                    self._agent_slots[agent] = slot
                slot.markdown(
                    f'<div class="aq-thinking">● {_esc(label)} 正在思考…</div>',
                    unsafe_allow_html=True,
                )
                return
            # 完成：把该分析师的状态行就地由「正在思考」改为「思考完成」，不再残留换行
            slot = self._agent_slots.pop(agent, None)
            if slot is not None:
                slot.markdown(
                    f'<div class="aq-done">✓ {_esc(label)} 思考完成</div>',
                    unsafe_allow_html=True,
                )
            if status == "completed":
                self.agents.append({"agent": agent, "payload": payload})
                card = _payload_card_html(payload)
                if card is not None:
                    self._body.markdown(card, unsafe_allow_html=True)
                dumped: Any = None
                if hasattr(payload, "model_dump"):
                    try:
                        dumped = payload.model_dump(mode="json")
                    except Exception:  # noqa: BLE001 - 序列化失败仅丢失回放细节
                        dumped = None
                self.trace_log.append({"kind": "agent", "agent": agent, "payload": dumped})
        except Exception:  # noqa: BLE001 - 渲染异常不影响流水线
            pass

    # ---------------- 内部 ----------------
    def _redraw_stepper(self) -> None:
        self._stepper_slot.markdown(_stepper_html(self.nodes), unsafe_allow_html=True)


# --------------------------------------------------------------- 回放 ----

_REPLAY_MODELS = {
    "fundamental": AnalystReport,
    "sentiment": AnalystReport,
    "news": AnalystReport,
    "technical": AnalystReport,
    "bull": DebateTurn,
    "bear": DebateTurn,
    "trader": TradeProposal,
    "risk": RiskAssessment,
    "pm": Decision,
}


def render_replay(trace_log: list[dict[str, Any]]) -> None:
    """rerun 后从 trace_log 重绘终态 stepper 与全部过程卡片。"""
    if not trace_log:
        return
    nodes: dict[str, dict[str, Any]] = {}
    cards: list[tuple[str, dict[str, Any]]] = []
    for entry in trace_log:
        if entry.get("kind") == "node" and entry.get("event") == "finished":
            nodes[entry["node"]] = {
                "status": entry.get("status") or "ok",
                "duration_ms": entry.get("duration_ms", 0.0),
            }
        elif entry.get("kind") == "agent" and entry.get("payload") is not None:
            cards.append((entry.get("agent", ""), entry["payload"]))

    st.markdown(_stepper_html(nodes), unsafe_allow_html=True)
    for index, (agent, data) in enumerate(cards):
        model = _REPLAY_MODELS.get(agent)
        if model is None:
            continue
        try:
            payload = model.model_validate(data)
        except Exception:  # noqa: BLE001 - 回放条目损坏时跳过该卡片
            continue
        card = _payload_card_html(payload)
        if card is not None:
            # 交错延迟仅在卡片数量可控时生效（首屏依次浮现）
            delay = min(index, 12) * 40
            if 'class="aq-card"' in card:
                card = card.replace(
                    'class="aq-card"',
                    f'class="aq-card" style="animation-delay:{delay}ms"',
                    1,
                )
            st.markdown(card, unsafe_allow_html=True)
