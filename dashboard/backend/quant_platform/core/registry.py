"""Small plugin registry used by strategies and portfolio constructors."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from quant_platform.core.exceptions import PluginError


class PluginRegistry:
    """Register and instantiate plugins by category and name."""

    def __init__(self) -> None:
        self._plugins: dict[tuple[str, str], Callable[..., Any]] = {}

    def register(self, category: str, name: str, factory: Callable[..., Any]) -> None:
        """Register a plugin factory, rejecting duplicate names."""

        key = (category, name)
        if key in self._plugins:
            raise PluginError(f"Plugin already registered: {category}/{name}")
        self._plugins[key] = factory

    def create(self, category: str, name: str, **kwargs: Any) -> Any:
        """Instantiate a previously registered plugin."""

        try:
            factory = self._plugins[(category, name)]
        except KeyError as exc:
            raise PluginError(f"Unknown plugin: {category}/{name}") from exc
        return factory(**kwargs)

    def names(self, category: str) -> tuple[str, ...]:
        """Return registered names for a category."""

        return tuple(sorted(name for cat, name in self._plugins if cat == category))
