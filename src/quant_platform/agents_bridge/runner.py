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
from trading_agents.config import TradingConfig
from trading_agents.execution import Portfolio, SimulatedExchange
from trading_agents.llm import create_llm_client
from trading_agents.memory import MemoryStore
from trading_agents.orchestrator import PipelineContext, PipelineState, run_pipeline
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
    ) -> None:
        self.llm_provider = llm_provider
        self.debate_rounds = int(debate_rounds)
        self.cache_dir = Path(cache_dir)
        self.use_cache = use_cache
        # http_proxy 置空：平台内集成时行情来自内存 DataFrame，无需代理。
        config = TradingConfig.load(base_dir=Path(base_dir), provider=llm_provider)
        config.market = "CN"
        config.debate_rounds = self.debate_rounds
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
            env_key_name=TradingConfig.env_key_name(config.llm.provider),
        )
        self._ctx_base = PipelineContext(
            config=config,
            llm=llm,
            provider=DataFrameProvider({}),  # 占位，每次 decide 时替换
            memory=MemoryStore(config.sqlite_path, config.memory_dir),
            exchange=SimulatedExchange(config.execution),
            portfolio=Portfolio(),
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
        self, symbol: str, trade_date: dt.date, history_df: pd.DataFrame
    ) -> PipelineState:
        """返回完整流水线状态（含报告/辩论/风控，供 Web 页面展示），不走缓存。"""
        ctx = self._build_context(symbol, history_df)
        try:
            state = run_pipeline(symbol, trade_date, ctx, resume=False)
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
        return PipelineContext(
            config=base.config,
            llm=base.llm,
            provider=DataFrameProvider({symbol: history_df}),
            memory=base.memory,
            exchange=base.exchange,
            portfolio=Portfolio(),  # 每次决策独立账户，避免跨标的互相影响
        )

    def _cache_key(self, symbol: str, trade_date: dt.date, history_df: pd.DataFrame) -> str:
        last_date = ""
        if not history_df.empty:
            last_date = str(pd.to_datetime(history_df["trade_date"]).max().date())
        raw = f"{self.llm_provider}|{self.debate_rounds}|{last_date}"
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
