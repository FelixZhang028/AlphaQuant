"""Agent 基类：prompt 加载、结构化 LLM 调用、token 统计。"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from trading_agents.llm import LLMClient, LLMResponse, Message

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(name: str) -> str:
    """从 prompts/ 目录加载 Agent 的独立 prompt 文件。"""
    path = PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")


class BaseAgent:
    """所有 Agent 的基类。``tag`` 用于 Mock LLM 调度与 trace。"""

    tag: str = "base"
    prompt_file: str = ""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self.last_response: LLMResponse | None = None

    @property
    def system_prompt(self) -> str:
        return load_prompt(self.prompt_file)

    def ask(
        self,
        user_content: str,
        response_model: type[BaseModel],
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> BaseModel:
        """发起一次结构化调用；输出经 Pydantic 强校验（失败由上层重试）。"""
        messages: list[Message] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"[AGENT:{self.tag}]\n{user_content}"},
        ]
        parsed, resp = self.llm.chat_structured(
            messages, response_model, temperature=temperature, max_tokens=max_tokens
        )
        self.last_response = resp
        return parsed
