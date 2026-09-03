"""Resolve and prepare configured market-data providers."""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path
from typing import Any

from quant_platform.agents_bridge.data_credentials import DataCredentialStore
from quant_platform.core.exceptions import DataUnavailableError
from quant_platform.data.providers.baostock_provider import BaoStockDataProvider
from quant_platform.data.providers.ifind_provider import IFindDataProvider
from quant_platform.data.providers.pytdx_provider import PyTdxDataProvider

logger = logging.getLogger(__name__)


class DataSourceResolver:
    """Keep provider routing, credentials, and environment loading cohesive."""

    def __init__(
        self,
        app_config_path: Path,
        source_config: dict[str, Any],
        *,
        ifind_client: Any | None = None,
        baostock_client: Any | None = None,
        pytdx_client_factory: Any | None = None,
    ) -> None:
        self.app_config_path = app_config_path
        self.source_config = source_config
        self.ifind_client = ifind_client
        self.baostock_client = baostock_client
        self.pytdx_client_factory = pytdx_client_factory

    def market_sources(self) -> list[str]:
        """Return enabled and routed sources for daily bars."""

        routing = self.source_config.get("routing", {})
        configured = routing.get("daily_bars", ["akshare"])
        providers = self.source_config.get("providers", {})
        enabled = [
            str(name)
            for name in configured
            if bool(providers.get(str(name), {}).get("enabled", True))
        ]
        return enabled or ["akshare"]

    def source_display_name(self, source: str) -> str:
        providers = self.source_config.get("providers", {})
        config = providers.get(source, {}) if isinstance(providers, dict) else {}
        return str(config.get("display_name", source)) if isinstance(config, dict) else source

    def resolve_market_sources(self, requested: list[str] | None) -> list[str]:
        """Validate a requested source order against the enabled route."""

        configured = self.market_sources()
        if requested is None:
            return configured
        unique = list(dict.fromkeys(str(source).strip().lower() for source in requested))
        unique = [source for source in unique if source]
        if not unique:
            raise ValueError("At least one market-data source must be selected")
        unavailable = [source for source in unique if source not in configured]
        if unavailable:
            raise ValueError(
                "Market-data sources are disabled or not routed for daily bars: "
                + ", ".join(unavailable)
            )
        return unique

    def fallback_enabled(self, requested: bool | None) -> bool:
        if requested is not None:
            return requested
        quality = self.source_config.get("quality", {})
        return bool(quality.get("allow_fallback_provider", True))

    def load_local_environment(self) -> None:
        """Load the first available local ``.env`` file without overwriting."""

        DataCredentialStore().load_into_environment()

        candidates = [
            Path.cwd() / ".env",
            self.app_config_path.parent / ".env",
            self.app_config_path.parent.parent / ".env",
        ]
        for path in dict.fromkeys(candidates):
            if not path.is_file():
                continue
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, value)
            return

    def ifind_provider(self) -> IFindDataProvider:
        self.load_local_environment()
        config = self.source_config.get("providers", {}).get("ifind", {})
        username_env = str(config.get("username_env", "IFIND_USERNAME"))
        password_env = str(config.get("password_env", "IFIND_PASSWORD"))
        username = os.getenv(username_env)
        password = os.getenv(password_env)
        if self.ifind_client is None and (not username or not password):
            raise DataUnavailableError(
                f"iFinD credentials are not configured in {username_env}/{password_env}"
            )
        return IFindDataProvider(
            username,
            password,
            client=self.ifind_client,
            batch_size=int(config.get("batch_size", 3)),
        )

    def baostock_provider(self) -> BaoStockDataProvider:
        return BaoStockDataProvider(client=self.baostock_client)

    def pytdx_provider(self) -> PyTdxDataProvider:
        """Build the optional PyTDX adapter from source configuration."""

        config = self.source_config.get("providers", {}).get("pytdx", {})
        return PyTdxDataProvider(
            servers=config.get("servers", []),
            timeout=float(config.get("timeout", 3.0)),
            retries=int(config.get("retries", 1)),
            max_servers=int(config.get("max_servers", 8)),
            max_pages=int(config.get("max_pages", 20)),
            client_factory=self.pytdx_client_factory,
        )

    def sdk_ready(self, module_name: str) -> bool:
        """Return whether an optional third-party SDK is importable."""

        try:
            return importlib.util.find_spec(module_name) is not None
        except (ImportError, ValueError):
            return False
