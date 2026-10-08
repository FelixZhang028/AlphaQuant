"""Local credentials used by optional market-data integrations."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_DATA_CREDENTIALS_PATH = Path("runtime/data_source_settings.json")


class DataCredentialStore:
    """Store data-source credentials locally without committing them to Git."""

    def __init__(self, path: str | Path = DEFAULT_DATA_CREDENTIALS_PATH) -> None:
        self.path = Path(path)

    def _read(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return value if isinstance(value, dict) else {}

    def get(self, provider: str) -> dict[str, str]:
        providers = self._read().get("providers", {})
        raw = providers.get(provider, {}) if isinstance(providers, dict) else {}
        if not isinstance(raw, dict):
            return {}
        return {str(key): str(value) for key, value in raw.items() if value is not None}

    def save(self, provider: str, **credentials: str) -> None:
        data = self._read()
        providers = data.setdefault("providers", {})
        providers[provider] = {
            key: value.strip() for key, value in credentials.items() if value.strip()
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def resolve(self, provider: str, field: str, env_name: str) -> str:
        """Resolve a local value first and fall back to an environment variable."""

        return self.get(provider).get(field, "") or os.getenv(env_name, "")

    def load_into_environment(self) -> None:
        """Expose saved local credentials to providers that already read environment keys."""

        mappings = {
            ("xtick", "token"): "XTICK_TOKEN",
            ("tushare", "token"): "TUSHARE_TOKEN",
            ("ifind", "username"): "IFIND_USERNAME",
            ("ifind", "password"): "IFIND_PASSWORD",
        }
        for (provider, field), env_name in mappings.items():
            value = self.get(provider).get(field, "")
            if value:
                os.environ[env_name] = value
