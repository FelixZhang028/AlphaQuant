"""发给文本模型的请求：DeepSeek 官方接口关闭思考模式（思考也算进 max_tokens，JSON 回答会被截断），
别的服务不加这个参数。"""

from __future__ import annotations

import requests

from app.quant import platform_ai


class Reply:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": "{}"}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}


def sent_payload(monkeypatch, base_url):
    sent = []
    monkeypatch.setattr(requests, "post", lambda url, **kwargs: sent.append((url, kwargs["json"])) or Reply())
    monkeypatch.setattr(platform_ai, "record_tokens", lambda prompt, completion: None)
    model = platform_ai.PlatformModel(base_url=base_url, model="some-model", api_key="k")
    platform_ai.model_client(model).chat([{"role": "user", "content": "hi"}], max_tokens=100)
    return sent[0]


def test_deepseek_thinking_is_turned_off(monkeypatch):
    for base in ("https://api.deepseek.com/v1", "https://api.deepseek.com", "https://API.DeepSeek.com/v1/"):
        url, payload = sent_payload(monkeypatch, base)
        assert payload["thinking"] == {"type": "disabled"} and payload["max_tokens"] == 100
        assert url.endswith("/chat/completions")


def test_other_services_get_the_plain_request(monkeypatch):
    for base in ("https://openrouter.ai/api/v1", "https://dashscope.aliyuncs.com/compatible-mode/v1",
                 "https://api.deepseek.com.example.org/v1"):
        _, payload = sent_payload(monkeypatch, base)
        assert "thinking" not in payload
        assert set(payload) == {"model", "messages", "temperature", "max_tokens"}
