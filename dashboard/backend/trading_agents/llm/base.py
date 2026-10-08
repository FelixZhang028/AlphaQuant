"""LLMClient 抽象基类、结构化输出校验与 Provider 注册表。

- ``chat``：自由文本对话。
- ``chat_structured``：要求模型输出 JSON，并用 Pydantic 模型强校验；
  校验失败抛 :class:`StructuredOutputError`，由编排层计入重试预算。
- Provider 注册表内置 openai / deepseek / qwen / glm / ollama / mock。
- API Key 仅从环境变量读取，未配置时明确报错。
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any, TypedDict

from pydantic import BaseModel, ValidationError


class Message(TypedDict):
    role: str  # system / user / assistant
    content: str


class LLMResponse(BaseModel):
    """一次 LLM 调用的统一返回。"""

    text: str
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0


class StructuredOutputError(RuntimeError):
    """LLM 输出无法通过 Pydantic 校验。"""


class LLMClient(ABC):
    """统一 LLM 接口。实现方不得执行模型输出的任何代码。"""

    name: str = "abstract"

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """自由文本对话。"""

    def chat_structured(
        self,
        messages: list[Message],
        response_model: type[BaseModel],
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> tuple[BaseModel, LLMResponse]:
        """结构化输出：把 JSON Schema 注入提示词，解析并强校验返回。"""
        schema = json.dumps(response_model.model_json_schema(), ensure_ascii=False)
        sys_extra: Message = {
            "role": "system",
            "content": (
                "你必须只输出一个符合以下 JSON Schema 的 JSON 对象，"
                "不要输出任何其他文字或代码块标记。\n" + schema
            ),
        }
        resp = self.chat([sys_extra, *messages], temperature=temperature, max_tokens=max_tokens)
        parsed = parse_structured(resp.text, response_model)
        return parsed, resp


def parse_structured(text: str, response_model: type[BaseModel]) -> BaseModel:
    """从模型文本中解析 JSON 并用 Pydantic 校验；失败抛 StructuredOutputError。"""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # 容错剥离 markdown 代码块
        lines = [ln for ln in cleaned.splitlines() if not ln.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    try:
        data: Any = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise StructuredOutputError(f"LLM output is not valid JSON: {exc}") from exc
    try:
        return response_model.model_validate(data)
    except ValidationError as exc:
        raise StructuredOutputError(f"LLM output failed schema validation: {exc}") from exc


# ---------------------------------------------------------------- 注册表 ----

ProviderFactory = type[LLMClient]
_REGISTRY: dict[str, ProviderFactory] = {}


def register_provider(name: str, cls: ProviderFactory) -> None:
    """注册一个 LLM Provider（可插拔，不影响任何 Agent 逻辑）。"""
    _REGISTRY[name] = cls


def create_llm_client(
    provider: str,
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    env_key_name: str = "",
) -> LLMClient:
    """按名称构造 LLM 客户端。需要 key 的 Provider 未配置时明确报错。"""
    if provider not in _REGISTRY:
        raise KeyError(f"unknown LLM provider: {provider!r}; registered: {sorted(_REGISTRY)}")
    cls = _REGISTRY[provider]
    if issubclass(cls, OpenAICompatClient):
        key = api_key or (os.environ.get(env_key_name, "") if env_key_name else "")
        if cls.requires_key and not key:
            raise RuntimeError(
                f"provider {provider!r} requires API key via env var {env_key_name}; "
                "未配置，无法调用真实模型。可改用 --llm mock 离线运行。"
            )
        return cls(model=model, base_url=base_url, api_key=key)
    return cls(model=model)  # type: ignore[call-arg]


class OpenAICompatClient(LLMClient):
    """任意 OpenAI 兼容端点（OpenAI / DeepSeek / Qwen / GLM / Ollama）。

    用 ``requests`` 直连 ``/chat/completions``，不依赖 openai SDK。
    子类通过类属性给出默认 base_url 与是否需要 key。
    """

    name = "openai_compat"
    default_base_url: str = "https://api.openai.com/v1"
    requires_key: bool = True

    def __init__(self, model: str, base_url: str | None = None, api_key: str = "") -> None:
        self.model = model
        self.base_url = (base_url or self.default_base_url).rstrip("/")
        self.api_key = api_key

    def chat(
        self,
        messages: list[Message],
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        import requests

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        resp = requests.post(
            f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=120
        )
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return LLMResponse(
            text=choice,
            model=data.get("model", self.model),
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
        )


class OpenAIClient(OpenAICompatClient):
    name = "openai"


class DeepSeekClient(OpenAICompatClient):
    name = "deepseek"
    default_base_url = "https://api.deepseek.com/v1"


class QwenClient(OpenAICompatClient):
    name = "qwen"
    default_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class GLMClient(OpenAICompatClient):
    name = "glm"
    default_base_url = "https://open.bigmodel.cn/api/paas/v4"


class OllamaClient(OpenAICompatClient):
    name = "ollama"
    default_base_url = "http://localhost:11434/v1"
    requires_key = False


class KimiClient(OpenAICompatClient):
    """Kimi 开放平台（OpenAI 兼容协议）。模型列表见 platform.kimi.com/docs/models。"""

    name = "kimi"
    default_base_url = "https://api.kimi.com/v1"


class CustomClient(OpenAICompatClient):
    """用户自定义 OpenAI 兼容端点。base_url 和 api_key 由调用方完全指定。"""

    name = "custom"
    default_base_url = ""


register_provider("openai", OpenAIClient)
register_provider("deepseek", DeepSeekClient)
register_provider("qwen", QwenClient)
register_provider("glm", GLMClient)
register_provider("ollama", OllamaClient)
register_provider("kimi", KimiClient)
register_provider("custom", CustomClient)


def _register_mock() -> None:
    from trading_agents.llm.mock import MockLLMClient

    register_provider("mock", MockLLMClient)


_register_mock()
