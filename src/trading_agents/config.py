"""配置中心：集中管理路径、LLM、执行与编排参数。

所有路径相对 ``base_dir``（默认 ``<cwd>/runs``），禁止硬编码用户主目录。
API Key 仅通过环境变量注入，代码中不得出现密钥。
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field

# 各 Provider 的合理默认模型名。仅当环境变量 TRADING_DEEP_MODEL / TRADING_QUICK_MODEL
# 未显式设置时使用；显式设置后以环境变量为准。避免出现「provider=deepseek 却传
# gpt-4o-mini 导致 400 Bad Request」这类模型名与端点不匹配的问题。
PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "mock": "mock-llm",
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
    "qwen": "qwen-plus",
    "glm": "glm-4-plus",
    "ollama": "qwen2.5:7b",
    "kimi": "kimi-k3",
}



class LLMSettings(BaseModel):
    """LLM 相关配置。``deep_think`` 用于复杂推理，``quick_think`` 用于轻量任务。"""

    provider: str = "mock"  # mock / openai / deepseek / qwen / glm / ollama
    deep_think_model: str = "gpt-4o-mini"
    quick_think_model: str = "gpt-4o-mini"
    temperature: float = 0.2
    max_tokens: int = 2048
    base_url: str | None = None  # OpenAI 兼容端点；None 表示用 Provider 默认值


class ExecutionSettings(BaseModel):
    """模拟交易所规则：滑点、手续费、T+1。"""

    slippage_bps: float = 5.0  # 滑点，万分之几
    commission_bps: float = 5.0  # 佣金，万分之几
    min_commission: float = 0.0
    settlement_days: int = 1  # T+1
    initial_cash: float = 100_000.0


class TradingConfig(BaseModel):
    """全局配置。可通过 ``TradingConfig.load`` 从环境变量构造。"""

    base_dir: Path = Field(default_factory=lambda: Path.cwd() / "runs")
    debate_rounds: int = 2
    max_llm_retries: int = 3
    node_retries: int = 1  # 每节点重试预算（不含 LLM 内部重试）
    timeout_seconds: int = 120
    checkpoint_enabled: bool = True
    debug: bool = False
    market: str = "US"
    analyst_dims: list[str] | None = None  # 选中的分析师维度；None=全部 4 个
    # 行情数据源代理（yfinance/curl_cffi 不读系统代理，需显式指定）。
    # 默认本机 Clash 端口；不需要代理时设为空字符串。
    http_proxy: str | None = "http://127.0.0.1:7897"
    llm: LLMSettings = Field(default_factory=LLMSettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)

    # ---- 派生路径 ----
    @property
    def sqlite_path(self) -> Path:
        return self.base_dir / "trading_agents.db"

    @property
    def trace_dir(self) -> Path:
        return self.base_dir / "traces"

    @property
    def memory_dir(self) -> Path:
        return self.base_dir / "memory"

    @property
    def artifacts_dir(self) -> Path:
        return self.base_dir / "artifacts"

    def ensure_dirs(self) -> None:
        for p in (self.base_dir, self.trace_dir, self.memory_dir, self.artifacts_dir):
            p.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def env_key_name(provider: str) -> str:
        """Provider 对应的环境变量名。"""
        return {
            "openai": "OPENAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "qwen": "DASHSCOPE_API_KEY",
            "glm": "ZHIPUAI_API_KEY",
            "kimi": "KIMI_API_KEY",
            "ollama": "",  # 本地模型无需 key
            "mock": "",
        }.get(provider, "OPENAI_COMPAT_API_KEY")

    @staticmethod
    def load(
        base_dir: str | Path | None = None,
        provider: str | None = None,
        debug: bool = False,
    ) -> TradingConfig:
        """从环境变量（可被参数覆盖）构造配置。"""
        llm_provider = provider or os.environ.get("TRADING_LLM_PROVIDER", "mock")
        default_model = PROVIDER_DEFAULT_MODELS.get(llm_provider, "gpt-4o-mini")
        llm = LLMSettings(
            provider=llm_provider,
            deep_think_model=os.environ.get("TRADING_DEEP_MODEL", default_model),
            quick_think_model=os.environ.get("TRADING_QUICK_MODEL", default_model),
            temperature=float(os.environ.get("TRADING_TEMPERATURE", "0.2")),
            base_url=os.environ.get("TRADING_LLM_BASE_URL") or None,
        )
        cfg = TradingConfig(
            base_dir=Path(base_dir or os.environ.get("TRADING_BASE_DIR", Path.cwd() / "runs")),
            debate_rounds=int(os.environ.get("TRADING_DEBATE_ROUNDS", "2")),
            max_llm_retries=int(os.environ.get("TRADING_MAX_LLM_RETRIES", "3")),
            checkpoint_enabled=os.environ.get("TRADING_CHECKPOINT", "1") == "1",
            debug=debug or os.environ.get("TRADING_DEBUG", "0") == "1",
            http_proxy=os.environ.get("TRADING_HTTP_PROXY", "http://127.0.0.1:7897") or None,
            llm=llm,
        )
        cfg.ensure_dirs()
        return cfg
