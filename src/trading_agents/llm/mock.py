"""MockLLMClient：确定性输出的离线 LLM。

无需 API key、无网络即可端到端跑通，供测试与演示使用。
调度方式：Agent 在用户消息首行放置 ``[AGENT:<name>]`` 标记，
Mock 按标记返回该角色的合法 JSON；其中价格类字段从提示词中的
``last_close=<数值>`` 提取，保证数字接地、不编造。
"""

from __future__ import annotations

import datetime as dt
import json
import re

from trading_agents.llm.base import LLMClient, LLMResponse, Message

_TAG_RE = re.compile(r"\[AGENT:([a-z_]+)\]")
_CLOSE_RE = re.compile(r"last_close=([0-9]+(?:\.[0-9]+)?)")
_DATE_RE = re.compile(r"trade_date=(\d{4}-\d{2}-\d{2})")
_TICKER_RE = re.compile(r"ticker=([A-Za-z0-9.\-]+)")


def _extract(pattern: re.Pattern[str], text: str, default: str) -> str:
    m = pattern.search(text)
    return m.group(1) if m else default


class MockLLMClient(LLMClient):
    """确定性 Mock：相同输入永远得到相同输出（temperature 无关）。"""

    name = "mock"

    def __init__(self, model: str = "mock-1") -> None:
        self.model = model
        self.calls: int = 0

    def chat(
        self,
        messages: list[Message],
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        self.calls += 1
        user_text = "\n".join(m["content"] for m in messages if m["role"] == "user")
        tag = _extract(_TAG_RE, user_text, "unknown")
        close = float(_extract(_CLOSE_RE, user_text, "100"))
        trade_date = _extract(_DATE_RE, user_text, str(dt.date.today()))
        ticker = _extract(_TICKER_RE, user_text, "UNKNOWN")
        payload = self._dispatch(tag, ticker, trade_date, close)
        text = json.dumps(payload, ensure_ascii=False)
        return LLMResponse(
            text=text,
            model=self.model,
            prompt_tokens=len(user_text) // 4,
            completion_tokens=len(text) // 4,
        )

    # ------------------------------------------------------------------ #
    def _dispatch(self, tag: str, ticker: str, trade_date: str, close: float) -> dict:
        analyst_dims = {"fundamental", "sentiment", "news", "technical"}
        if tag in analyst_dims:
            return self._analyst(tag, ticker, trade_date, close)
        if tag in {"bull", "bear"}:
            return self._debater(tag)
        if tag == "trader":
            return self._trader(ticker, trade_date, close)
        if tag == "risk":
            return self._risk()
        if tag == "pm":
            return self._pm()
        return {"summary": f"mock response for {tag}"}

    @staticmethod
    def _analyst(dim: str, ticker: str, trade_date: str, close: float) -> dict:
        return {
            "dimension": dim,
            "ticker": ticker,
            "as_of_date": trade_date,
            "summary": f"[mock] {dim} 维度分析：基于快照 last_close={close} 的中性偏多判断。",
            "key_findings": [
                {
                    "claim": f"{dim} 维度信号温和偏多",
                    "evidence": f"snapshot last_close={close}",
                    "source": "MarketSnapshot.last_close",
                }
            ],
            "score": 0.2,
            "confidence": 0.6,
            "red_flags": [],
        }

    @staticmethod
    def _debater(stance: str) -> dict:
        bullish = stance == "bull"
        return {
            "argument": (
                f"[mock] {'看多' if bullish else '看空'}论点："
                f"估值与动量{'支撑上行' if bullish else '暗示回调'}。"
            ),
            "response_to_opponent": (
                f"[mock] 部分认同对方关于{'风险' if bullish else '价值'}的观点，"
                "但证据强度不足。"
            ),
            "evidence": ["MarketSnapshot.last_close", "analyst reports"],
        }

    @staticmethod
    def _trader(ticker: str, trade_date: str, close: float) -> dict:
        return {
            "ticker": ticker,
            "as_of_date": trade_date,
            "action": "buy",
            "position_pct": 0.1,
            "entry_price": close,
            "stop_loss": round(close * 0.95, 4),
            "target_price": round(close * 1.1, 4),
            "holding_horizon": "swing",
            "rationale": (
                "[mock] 综合四份 AnalystReport 与辩论记录"
                "（技术面偏多，引用 last_close）。"
            ),
            "confidence": 0.6,
            "source_reports": ["fundamental", "sentiment", "news", "technical"],
        }

    @staticmethod
    def _risk() -> dict:
        return {
            "max_drawdown_est": 0.08,
            "volatility_level": "medium",
            "liquidity_concern": False,
            "concentration_risk": "low",
            "veto": False,
            "veto_reason": "",
            "conditions": ["仓位不得超过 20%"],
            "commentary": "[mock] 风险可控。",
        }

    @staticmethod
    def _pm() -> dict:
        return {
            "status": "approved",
            "final_position_pct": 0.1,
            "conditions": [],
            "rationale": "[mock] 提案与风控评估一致，批准。",
            "rejection_reason": "",
        }
