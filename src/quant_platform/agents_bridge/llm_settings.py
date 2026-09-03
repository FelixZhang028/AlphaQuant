"""LLM Provider 本地配置：Base URL / API Key / 模型，仅保存在本地运行时目录。

借鉴 AlphaMaster ``web_settings.json`` 的本地 AI 配置模式：

- API Key 以明文保存在 ``runtime/llm_settings.json``（已加入 .gitignore，绝不提交）；
- 页面会向用户承诺「API Key 仅保存在本地」；
- 环境变量仅作为回退来源，本地保存值优先；
- 模型列表按各 Provider 官方命名维护，可通过修改 :data:`PROVIDER_CATALOG` 增删。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_SETTINGS_PATH = Path("runtime/llm_settings.json")


@dataclass(frozen=True)
class ProviderSpec:
    """一个 LLM Provider 的静态描述：端点、环境变量、模型列表与默认模型。"""

    key: str
    display_name: str
    icon: str
    default_base_url: str
    env_key_name: str
    models: tuple[str, ...] = ()
    default_model: str = ""
    requires_key: bool = True


PROVIDER_CATALOG: dict[str, ProviderSpec] = {
    "mock": ProviderSpec(
        "mock", "Mock 离线", "🧪", "", "", (), "mock-llm", requires_key=False
    ),
    "openai": ProviderSpec(
        "openai",
        "OpenAI",
        "🅾️",
        "https://api.openai.com/v1",
        "OPENAI_API_KEY",
        ("gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"),
        "gpt-4o-mini",
    ),
    "deepseek": ProviderSpec(
        "deepseek",
        "DeepSeek",
        "🔮",
        "https://api.deepseek.com/v1",
        "DEEPSEEK_API_KEY",
        ("deepseek-v4-pro", "deepseek-v4-flash", "deepseek-chat", "deepseek-reasoner"),
        "deepseek-v4-pro",
    ),
    "kimi": ProviderSpec(
        "kimi",
        "Kimi（Moonshot）",
        "🌙",
        "https://api.kimi.com/v1",
        "KIMI_API_KEY",
        (
            "kimi-k2.6",
            "kimi-k3",
            "kimi-k2-turbo-preview",
            "moonshot-v1-8k",
            "moonshot-v1-32k",
            "moonshot-v1-128k",
        ),
        "kimi-k2.6",
    ),
    "qwen": ProviderSpec(
        "qwen",
        "通义千问",
        "🌀",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "DASHSCOPE_API_KEY",
        ("qwen-plus", "qwen-max", "qwen-turbo", "qwen-long"),
        "qwen-plus",
    ),
    "glm": ProviderSpec(
        "glm",
        "智谱 GLM",
        "📐",
        "https://open.bigmodel.cn/api/paas/v4",
        "ZHIPUAI_API_KEY",
        ("glm-4-plus", "glm-4-flash", "glm-4-air", "glm-4-long"),
        "glm-4-plus",
    ),
    "ollama": ProviderSpec(
        "ollama",
        "Ollama 本地",
        "🖥️",
        "http://localhost:11434/v1",
        "",
        ("qwen2.5:7b", "llama3.1:8b", "deepseek-r1:7b"),
        "qwen2.5:7b",
        requires_key=False,
    ),
    "custom": ProviderSpec(
        "custom",
        "自定义（OpenAI 兼容）",
        "⚙️",
        "",
        "OPENAI_COMPAT_API_KEY",
        (),
        "gpt-4o-mini",
    ),
}


class LLMSettingsStore:
    """读写 ``runtime/llm_settings.json``；API Key 只落在本地磁盘。"""

    def __init__(self, path: str | Path = DEFAULT_SETTINGS_PATH) -> None:
        self.path = Path(path)

    def _read(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def get(self, provider: str) -> dict[str, str]:
        """返回某 Provider 已保存的原始值（可能为空字符串）。"""
        providers = self._read().get("providers", {})
        entry = providers.get(provider, {}) if isinstance(providers, dict) else {}
        if not isinstance(entry, dict):
            entry = {}
        return {
            "base_url": str(entry.get("base_url", "")),
            "api_key": str(entry.get("api_key", "")),
            "model": str(entry.get("model", "")),
        }

    def get_default_provider(self) -> str:
        provider = str(self._read().get("default_provider", "mock"))
        return provider if provider in PROVIDER_CATALOG else "mock"

    def save_default_provider(self, provider: str) -> None:
        if provider not in PROVIDER_CATALOG:
            raise ValueError(f"Unknown LLM provider: {provider}")
        data = self._read()
        data["default_provider"] = provider
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def save(
        self, provider: str, *, base_url: str, api_key: str, model: str
    ) -> None:
        """把 Base URL / API Key / 模型写入本地设置文件。"""
        data = self._read()
        providers = data.setdefault("providers", {})
        providers[provider] = {
            "base_url": base_url,
            "api_key": api_key,
            "model": model,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def resolve(self, provider: str) -> dict[str, str]:
        """合并本地保存值 + Provider 默认值 + 环境变量回退（本地优先）。"""
        spec = PROVIDER_CATALOG[provider]
        local = self.get(provider)
        api_key = local["api_key"] or (
            os.environ.get(spec.env_key_name, "") if spec.env_key_name else ""
        )
        return {
            "base_url": local["base_url"] or spec.default_base_url,
            "api_key": api_key,
            "model": local["model"] or spec.default_model,
        }
