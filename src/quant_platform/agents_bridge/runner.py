"""AgentRunner：在 AlphaQuant 内复用 trading_agents 决策流水线的薄封装。

负责装配 TradingConfig / LLM client / MemoryStore / SimulatedExchange /
Portfolio（参考 trading_agents/cli.py 的 build_context），并提供基于磁盘的
决策缓存，避免回测中重复调用 LLM。
"""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

import pandas as pd

from quant_platform.agents_bridge.provider import DataFrameProvider
from quant_platform.agents_bridge.sources import NewsAwareProvider
from trading_agents.config import TradingConfig
from trading_agents.data.akshare_provider import AkshareProvider
from trading_agents.data.base import DataProvider
from trading_agents.data.eastmoney import EastMoneyProvider
from trading_agents.data.tonghuashun import TonghuashunProvider
from trading_agents.data.yfinance_provider import YFinanceProvider
from trading_agents.execution import Portfolio, SimulatedExchange
from trading_agents.llm import create_llm_client
from trading_agents.memory import MemoryStore
from trading_agents.orchestrator import (
    PipelineContext,
    PipelineState,
    run_pipeline,
)
from trading_agents.orchestrator.events import AgentReporter, EventBus
from trading_agents.schemas import Decision


class AgentRunner:
    """对单个标的跑一次 LLM 多智能体决策流水线。"""

    def __init__(
        self,
        llm_provider: str = "mock",
        debate_rounds: int = 1,
        base_dir: Path = Path("runtime/agent_runs"),
        cache_dir: Path = Path("runtime/agent_cache"),
        use_cache: bool = True,
        initial_cash: float = 100_000.0,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        prior_knowledge: str = "",
        stock_source: str = "local",
        news_sources: tuple[str, ...] = (),
        proxy_enabled: bool = True,
        proxy_address: str = "http://127.0.0.1:7897",
    ) -> None:
        self.llm_provider = llm_provider
        self.debate_rounds = int(debate_rounds)
        self.cache_dir = Path(cache_dir)
        self.use_cache = use_cache
        self.prior_knowledge = prior_knowledge
        self.stock_source = stock_source
        self.news_sources = tuple(news_sources)
        self.proxy_enabled = proxy_enabled
        self.proxy_address = proxy_address
        config = TradingConfig.load(base_dir=Path(base_dir), provider=llm_provider)
        config.market = "CN"
        config.debate_rounds = self.debate_rounds
        # 仅海外源（yfinance）走代理；local/AkShare/同花顺/东财行情无需代理。
        if stock_source == "yfinance" and proxy_enabled:
            config.http_proxy = proxy_address
        else:
            config.http_proxy = ""
        config.execution.initial_cash = float(initial_cash)

        # 自定义模型：允许用户覆盖 base_url 和 model
        if base_url:
            config.llm.base_url = base_url
        if model:
            config.llm.deep_think_model = model
            config.llm.quick_think_model = model

        self.config = config
        llm = create_llm_client(
            config.llm.provider,
            model=config.llm.deep_think_model,
            base_url=config.llm.base_url,
            api_key=api_key,
            env_key_name=TradingConfig.env_key_name(config.llm.provider),
        )
        self._ctx_base = PipelineContext(
            config=config,
            llm=llm,
            provider=DataFrameProvider({}),  # 占位，每次 decide 时替换
            memory=MemoryStore(config.sqlite_path, config.memory_dir),
            exchange=SimulatedExchange(config.execution),
            portfolio=Portfolio(),
            prior_knowledge=self.prior_knowledge,
        )

    # ------------------------------------------------------------------ #
    def decide(
        self, symbol: str, trade_date: dt.date, history_df: pd.DataFrame
    ) -> Decision:
        """返回最终决策；流水线失败或 decision 为空时抛 RuntimeError。"""
        if self.use_cache:
            cached = self._read_cache(symbol, trade_date, history_df)
            if cached is not None:
                return cached
        decision = self.decide_full(symbol, trade_date, history_df).decision
        if decision is None:
            raise RuntimeError(f"流水线未产出决策: {symbol} @ {trade_date}")
        if self.use_cache:
            self._write_cache(symbol, trade_date, history_df, decision)
        return decision

    def decide_full(
        self,
        symbol: str,
        trade_date: dt.date,
        history_df: pd.DataFrame,
        *,
        event_bus: EventBus | None = None,
        reporter: AgentReporter | None = None,
    ) -> PipelineState:
        """返回完整流水线状态（含报告/辩论/风控，供 Web 页面展示），不走缓存。

        ``event_bus`` / ``reporter`` 为可选的实时订阅通道：分别接收节点级
        NodeEvent 与 agent 级进度回调（供 Web 页面实时渲染分析过程）；
        默认 None 时行为与之前完全一致。
        """
        ctx = self._build_context(symbol, history_df)
        ctx.agent_reporter = reporter
        try:
            state = run_pipeline(symbol, trade_date, ctx, resume=False, event_bus=event_bus)
        except RuntimeError as exc:
            raise RuntimeError(
                f"LLM 决策流水线失败: {symbol} @ {trade_date}: {exc}"
            ) from exc
        if state.decision is None:
            raise RuntimeError(
                f"流水线未产出决策: {symbol} @ {trade_date}: {state.error or '未知原因'}"
            )
        return state

    # ------------------------------------------------------------------ #
    def _build_context(self, symbol: str, history_df: pd.DataFrame) -> PipelineContext:
        base = self._ctx_base
        stock = self._build_stock_provider(symbol, history_df)
        return PipelineContext(
            config=base.config,
            llm=base.llm,
            provider=NewsAwareProvider(stock, self.news_sources),
            memory=base.memory,
            exchange=base.exchange,
            portfolio=Portfolio(),  # 每次决策独立账户，避免跨标的互相影响
            prior_knowledge=self.prior_knowledge,
        )

    def _build_stock_provider(
        self, symbol: str, history_df: pd.DataFrame
    ) -> DataProvider:
        if self.stock_source == "eastmoney":
            return EastMoneyProvider(cache_path=self.cache_dir / "eastmoney_bars")
        if self.stock_source == "akshare":
            return AkshareProvider(cache_path=self.cache_dir / "akshare_bars")
        if self.stock_source == "tonghuashun":
            return TonghuashunProvider(cache_path=self.cache_dir / "tonghuashun_bars")
        if self.stock_source == "yfinance":
            return YFinanceProvider(proxy=self.config.http_proxy or None)
        return DataFrameProvider({symbol: history_df})

    def _cache_key(self, symbol: str, trade_date: dt.date, history_df: pd.DataFrame) -> str:
        last_date = ""
        if not history_df.empty:
            last_date = str(pd.to_datetime(history_df["trade_date"]).max().date())
        raw = (
            f"{self.llm_provider}|{self.debate_rounds}|{self.stock_source}|"
            f"{','.join(self.news_sources)}|{last_date}"
        )
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
        return f"{symbol}_{trade_date.isoformat()}_{digest}"

    def _read_cache(
        self, symbol: str, trade_date: dt.date, history_df: pd.DataFrame
    ) -> Decision | None:
        path = self.cache_dir / f"{self._cache_key(symbol, trade_date, history_df)}.json"
        if not path.is_file():
            return None
        try:
            return Decision.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            return None  # 缓存损坏时按未命中处理，重新调用

    def _write_cache(
        self, symbol: str, trade_date: dt.date, history_df: pd.DataFrame, decision: Decision
    ) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / f"{self._cache_key(symbol, trade_date, history_df)}.json"
        path.write_text(decision.model_dump_json(), encoding="utf-8")

    def battle(self, context: str, user_message: str) -> str:
        """带分析上下文的自由对话交锋；返回 AI 回应文本。"""
        system = (
            "你是一位严谨客观的量化分析师。用户会对你的分析结论提出观点或质疑，"
            "请基于给定的分析上下文理性回应：同意、反驳或修正立场，并给出依据。"
            "不盲从、不固执，保持专业克制。"
        )
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": f"[分析上下文]\n{context}\n\n[用户观点/质疑]\n{user_message}",
            },
        ]
        return self._ctx_base.llm.chat(messages, temperature=0.4, max_tokens=1024).text
