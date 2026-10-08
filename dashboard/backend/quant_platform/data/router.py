"""Configured primary/fallback provider routing."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import pandas as pd

from quant_platform.core.exceptions import (
    DataCapabilityNotSupported,
    DataUnavailableError,
)
from quant_platform.data.interfaces import DataProvider

logger = logging.getLogger(__name__)


class DataRouter:
    """Try providers in configured order and report the provider actually used."""

    def __init__(self, providers: dict[str, DataProvider], routes: dict[str, list[str]]) -> None:
        self.providers = providers
        self.routes = routes

    def fetch(
        self,
        dataset: str,
        method: str,
        *,
        allow_empty: bool = False,
        **kwargs: Any,
    ) -> tuple[pd.DataFrame, str]:
        """Call a provider method according to the route for a dataset."""

        failures: list[str] = []
        for provider_name in self.routes.get(dataset, []):
            provider = self.providers.get(provider_name)
            if provider is None:
                failures.append(f"{provider_name}: not configured")
                continue
            try:
                fetcher: Callable[..., pd.DataFrame] = getattr(provider, method)
                frame = fetcher(**kwargs)
                if frame.empty and not allow_empty:
                    failures.append(f"{provider_name}: empty result")
                    continue
                return frame, provider_name
            except DataCapabilityNotSupported as exc:
                failures.append(f"{provider_name}: {exc}")
            except Exception as exc:
                logger.exception("Provider fetch failed: %s/%s", provider_name, dataset)
                failures.append(f"{provider_name}: {type(exc).__name__}: {exc}")
        raise DataUnavailableError(f"No provider returned {dataset}; " + "; ".join(failures))
