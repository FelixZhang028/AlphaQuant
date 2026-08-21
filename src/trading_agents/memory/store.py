"""MemoryStore：按 ticker 沉淀决策日志，并生成/注入跨期反思。

- SQLite ``decision_log`` 表：结构化决策记录（含实现收益与 alpha，可后补）。
- Markdown 文件 ``memory/<TICKER>.md``：人类可读记忆。
- :meth:`context_for` 把最近 N 条决策 + 反思渲染为提示词片段，注入 Trader。
- 反思为规则化生成（什么有效、什么无效），确定性、可测试。
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

from trading_agents.schemas import Decision, MemoryEntry
from trading_agents.schemas.models import ApprovalStatus, TradeAction

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decision_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    action TEXT NOT NULL,
    position_pct REAL NOT NULL,
    status TEXT NOT NULL,
    realized_return REAL,
    alpha REAL,
    reflection TEXT,
    decision_json TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_decision_ticker ON decision_log(ticker, trade_date);
"""


def make_reflection(action: TradeAction, realized_return: float | None, alpha: float | None) -> str:
    """根据实现收益生成一段规则化反思。"""
    if realized_return is None:
        return "上次决策尚无实现收益数据，暂无法评估有效性。"
    if realized_return > 0.01:
        alpha_txt = f"{alpha:+.2%}" if alpha is not None else "N/A"
        return (
            f"上次 {action.value} 决策实现收益 {realized_return:+.2%}"
            f"（alpha {alpha_txt}），策略有效，可参考延续类似信号。"
        )
    if realized_return < -0.01:
        return (
            f"上次 {action.value} 决策实现收益 {realized_return:+.2%}，策略失效；"
            "本次应更谨慎对待同方向信号，检查当时的 red_flags 是否被忽略。"
        )
    return f"上次 {action.value} 决策收益接近持平（{realized_return:+.2%}），信号强度一般。"


class MemoryStore:
    def __init__(self, db_path: Path, memory_dir: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        memory_dir.mkdir(parents=True, exist_ok=True)
        self.memory_dir = memory_dir
        self._conn = sqlite3.connect(str(db_path))
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------ 写入 ----
    def record(self, decision: Decision) -> MemoryEntry:
        """追加一条决策日志（SQLite + Markdown）。"""
        entry = MemoryEntry(
            ticker=decision.ticker,
            trade_date=decision.trade_date,
            action=decision.final_action,
            position_pct=decision.final_position_pct,
            status=decision.status,
            reflection="",
            decision_json=decision.model_dump_json(),
            created_at=dt.datetime.now(dt.UTC),
        )
        cur = self._conn.execute(
            "INSERT INTO decision_log (ticker, trade_date, action, position_pct, status,"
            " realized_return, alpha, reflection, decision_json, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                entry.ticker, entry.trade_date.isoformat(), entry.action.value,
                entry.position_pct, entry.status.value, entry.realized_return,
                entry.alpha, entry.reflection, entry.decision_json,
                entry.created_at.isoformat(),
            ),
        )
        self._conn.commit()
        entry.id = int(cur.lastrowid or 0)
        self._append_markdown(entry, decision)
        return entry

    def update_outcome(
        self, ticker: str, realized_return: float, alpha: float | None
    ) -> None:
        """回填最近一次有仓位决策的实现收益与反思。"""
        row = self._conn.execute(
            "SELECT id, action FROM decision_log WHERE ticker=? AND realized_return IS NULL"
            " AND action != 'hold' ORDER BY id DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        if not row:
            return
        action = TradeAction(row[1])
        reflection = make_reflection(action, realized_return, alpha)
        self._conn.execute(
            "UPDATE decision_log SET realized_return=?, alpha=?, reflection=? WHERE id=?",
            (realized_return, alpha, reflection, row[0]),
        )
        self._conn.commit()

    # ------------------------------------------------------------ 读取 ----
    def history(self, ticker: str, limit: int = 5) -> list[MemoryEntry]:
        rows = self._conn.execute(
            "SELECT id, ticker, trade_date, action, position_pct, status, realized_return,"
            " alpha, reflection, decision_json, created_at FROM decision_log"
            " WHERE ticker=? ORDER BY id DESC LIMIT ?",
            (ticker, limit),
        ).fetchall()
        return [
            MemoryEntry(
                id=r[0], ticker=r[1], trade_date=dt.date.fromisoformat(r[2]),
                action=TradeAction(r[3]), position_pct=r[4],
                status=ApprovalStatus(r[5]), realized_return=r[6], alpha=r[7],
                reflection=r[8] or "", decision_json=r[9] or "",
                created_at=dt.datetime.fromisoformat(r[10]) if r[10] else None,
            )
            for r in rows
        ]

    def context_for(self, ticker: str, limit: int = 3) -> str:
        """渲染注入 Trader 的历史决策 + 反思片段；无历史时返回空串。"""
        entries = self.history(ticker, limit=limit)
        if not entries:
            return ""
        lines = []
        for e in entries:
            ret = f"{e.realized_return:+.2%}" if e.realized_return is not None else "未结算"
            lines.append(
                f"- {e.trade_date}: {e.action.value} {e.position_pct:.0%} ({e.status.value})"
                f" 实现收益={ret}"
                + (f"\n  反思: {e.reflection}" if e.reflection else "")
            )
        return "\n".join(lines)

    # ------------------------------------------------------------ 内部 ----
    def _append_markdown(self, entry: MemoryEntry, decision: Decision) -> None:
        path = self.memory_dir / f"{entry.ticker}.md"
        with path.open("a", encoding="utf-8") as f:
            f.write(
                f"\n## {entry.trade_date} — {entry.action.value}"
                f" {entry.position_pct:.0%} [{entry.status.value}]\n\n"
            )
            for link in decision.rationale_chain:
                f.write(f"- {link}\n")
            if decision.rejection_reason:
                f.write(f"- 驳回原因: {decision.rejection_reason}\n")

    def close(self) -> None:
        self._conn.close()
