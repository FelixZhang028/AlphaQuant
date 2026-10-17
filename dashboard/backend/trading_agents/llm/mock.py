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

# ---- 自然语言建策略：常见中文描述模式（确定性解析，供离线演示） ----
_NL_MA_RE = re.compile(r"(\d+)\s*日均线")
_NL_AMOUNT_RE = re.compile(
    r"(?:(\d+)\s*日)?平均成交额[^0-9%，。；%]{0,8}(?:大于|超过|高于)(\d+(?:\.\d+)?)(万|亿)?"
)
_NL_PCT_RE = re.compile(
    r"(\d+)\s*日(?:涨跌幅|涨幅|跌幅)(?:超过|大于|高于|低于|小于)(\d+(?:\.\d+)?)%"
)
_NL_BREAKOUT_RE = re.compile(r"突破(?:过去)?(\d+)\s*日(?:最高价|最高)")
_NL_RANK_RE = re.compile(r"按(\d+)\s*日(涨跌幅|涨幅|跌幅|波动率|平均成交额|成交额)")


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
        system_text = "\n".join(m["content"] for m in messages if m["role"] == "system")
        if "[分析上下文]" in system_text:
            return self._battle_reply(messages)
        if "量化策略助手" in system_text:
            return self._nl_strategy_reply(messages)
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

    def _battle_reply(self, messages: list[Message]) -> LLMResponse:
        """人机交锋：返回自然语言回应（而非结构化 JSON）。"""
        user_msgs = [str(m["content"]) for m in messages if m["role"] == "user"]
        question = user_msgs[-1] if user_msgs else ""
        rounds = max(0, len(user_msgs) - 1)
        challenges = "风险" in question or "质疑" in question
        stance = "部分修正立场" if challenges else "维持原有结论"
        text = (
            f"[mock 交锋·第{rounds + 1}轮] 收到你的观点：「{question[:48]}」。"
            f"基于当前分析上下文与此前 {rounds} 轮交锋，我{stance}："
            "若你能补充新的数据、事件或逻辑证据，我会相应调整判断。"
        )
        return LLMResponse(
            text=text,
            model=self.model,
            prompt_tokens=len(question) // 4,
            completion_tokens=len(text) // 4,
        )

    def _nl_strategy_reply(self, messages: list[Message]) -> LLMResponse:
        """自然语言建策略：确定性解析常见中文模式，返回合法策略草稿 JSON。"""
        user_msgs = [str(m["content"]) for m in messages if m["role"] == "user"]
        description = re.sub(r"^策略描述：", "", user_msgs[0]).strip() if user_msgs else ""
        payload = _parse_nl_description(description)
        text = json.dumps(payload, ensure_ascii=False)
        return LLMResponse(
            text=text,
            model=self.model,
            prompt_tokens=len(description) // 4,
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


def _parse_nl_description(description: str) -> dict:
    """把常见中文策略描述解析为 NLStrategyDraft 兼容的 JSON（离线演示用）。

    无法识别的模式回退到「5日均线高于20日均线」默认规则，
    保证输出始终能通过平台校验。
    """
    rules: list[dict] = []

    # 均线：两条 -> 短高于长；一条 -> 收盘价站上均线
    ma_windows = sorted({int(w) for w in _NL_MA_RE.findall(description)})
    if len(ma_windows) >= 2:
        rules.append(
            {
                "left": {"name": "moving_average", "window": ma_windows[0]},
                "operator": "greater_than",
                "right": {"name": "moving_average", "window": ma_windows[1]},
            }
        )
    elif len(ma_windows) == 1:
        rules.append(
            {
                "left": {"name": "close"},
                "operator": "greater_than",
                "right": {"name": "moving_average", "window": ma_windows[0]},
            }
        )

    # 平均成交额阈值（单位归一到元）
    m = _NL_AMOUNT_RE.search(description)
    if m:
        window = int(m.group(1)) if m.group(1) else 5
        value = float(m.group(2))
        if m.group(3) == "万":
            value *= 10_000
        elif m.group(3) == "亿":
            value *= 100_000_000
        rules.append(
            {
                "left": {"name": "average_amount", "window": window},
                "operator": "greater_than",
                "value": value,
            }
        )

    # 涨跌幅阈值（跌幅取负值配合小于）
    m = _NL_PCT_RE.search(description)
    if m:
        window = int(m.group(1))
        threshold = float(m.group(2)) / 100
        falling = "跌幅" in m.group(0)
        rules.append(
            {
                "left": {"name": "return", "window": window},
                "operator": "less_than" if falling else "greater_than",
                "value": -threshold if falling else threshold,
            }
        )

    # 收盘价突破前高
    m = _NL_BREAKOUT_RE.search(description)
    if m:
        rules.append(
            {
                "left": {"name": "close"},
                "operator": "greater_than",
                "right": {"name": "previous_high", "window": int(m.group(1))},
            }
        )

    if not rules:
        rules.append(
            {
                "left": {"name": "moving_average", "window": 5},
                "operator": "greater_than",
                "right": {"name": "moving_average", "window": 20},
            }
        )

    # 排序：默认按20日涨幅从高到低
    ranking = {"indicator": {"name": "return", "window": 20}, "direction": "descending"}
    m = _NL_RANK_RE.search(description)
    if m:
        kind = m.group(2)
        indicator_name = "return"
        if kind in ("平均成交额", "成交额"):
            indicator_name = "average_amount"
        elif kind == "波动率":
            indicator_name = "volatility"
        descending = not any(
            keyword in description for keyword in ("从低到高", "从弱到强", "从小到大")
        )
        if kind == "跌幅" and any(
            keyword in description for keyword in ("从大到小", "从高到低")
        ):
            descending = False
        ranking = {
            "indicator": {"name": indicator_name, "window": int(m.group(1))},
            "direction": "descending" if descending else "ascending",
        }

    return {
        "strategy_id": "nl_mock_strategy",
        "name": "自然语言解析策略",
        "description": description[:80],
        "entry_logic": "all",
        "entry_rules": rules,
        "ranking": ranking,
    }
