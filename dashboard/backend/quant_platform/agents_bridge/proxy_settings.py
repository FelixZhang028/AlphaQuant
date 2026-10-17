"""网络代理本地配置：海外数据源（yfinance）请求时使用的 HTTP 代理。

与 ``llm_settings.py`` 同模式：JSON 落 ``runtime/``（已 gitignore），
读坏文件回退默认值。默认指向本机 Clash 端口 7897。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_PROXY_PATH = Path("runtime/proxy_settings.json")
DEFAULT_PROXY_ADDRESS = "http://127.0.0.1:7897"


class ProxySettingsStore:
    """读写 ``runtime/proxy_settings.json``；损坏或缺失时回退默认值。"""

    def __init__(self, path: str | Path = DEFAULT_PROXY_PATH) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        """返回 ``{"enabled": bool, "address": str}``；异常时回退默认值。"""
        defaults: dict[str, Any] = {"enabled": True, "address": DEFAULT_PROXY_ADDRESS}
        if not self.path.is_file():
            return defaults
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return defaults
        if not isinstance(data, dict):
            return defaults
        return {
            "enabled": bool(data.get("enabled", True)),
            "address": str(data.get("address", DEFAULT_PROXY_ADDRESS))
            or DEFAULT_PROXY_ADDRESS,
        }

    def save(self, enabled: bool, address: str) -> None:
        """把代理开关与地址写入本地设置文件。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"enabled": bool(enabled), "address": address.strip()}
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
