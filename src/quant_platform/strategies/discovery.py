"""Automatic discovery and construction of strategy plugins."""

from __future__ import annotations

import inspect
import pkgutil
from importlib import import_module
from typing import Any

from quant_platform.core.exceptions import PluginError
from quant_platform.strategies.base import Strategy
from quant_platform.strategies.spec import StrategyMetadata


class StrategyCatalog:
    """Discover concrete Strategy subclasses from a Python package."""

    def __init__(self, package_name: str = "quant_platform.strategies") -> None:
        self.package_name = package_name
        self._strategies = self._discover()

    def _discover(self) -> dict[str, type[Strategy]]:
        package = import_module(self.package_name)
        package_paths = getattr(package, "__path__", None)
        if package_paths is None:
            raise PluginError(f"Strategy package has no package path: {self.package_name}")
        discovered: dict[str, type[Strategy]] = {}
        for module_info in pkgutil.iter_modules(package_paths):
            if module_info.name.startswith("_"):
                continue
            module = import_module(f"{self.package_name}.{module_info.name}")
            for _, candidate in inspect.getmembers(module, inspect.isclass):
                if (
                    candidate is Strategy
                    or not issubclass(candidate, Strategy)
                    or inspect.isabstract(candidate)
                    or candidate.__module__ != module.__name__
                ):
                    continue
                plugin_name = getattr(candidate, "plugin_name", "").strip()
                if not plugin_name:
                    raise PluginError(
                        f"Strategy class is missing plugin_name: {candidate.__name__}"
                    )
                if plugin_name in discovered:
                    raise PluginError(f"Duplicate strategy plugin: {plugin_name}")
                discovered[plugin_name] = candidate
        if not discovered:
            raise PluginError(f"No strategies discovered in {self.package_name}")
        return discovered

    def names(self) -> tuple[str, ...]:
        """Return stable plugin identifiers."""

        return tuple(sorted(self._strategies))

    def metadata(self) -> tuple[StrategyMetadata, ...]:
        """Return all strategy descriptions sorted by plugin name."""

        return tuple(self._strategies[name].metadata() for name in self.names())

    def get_metadata(self, plugin_name: str) -> StrategyMetadata:
        """Return metadata for one plugin."""

        try:
            return self._strategies[plugin_name].metadata()
        except KeyError as exc:
            raise PluginError(f"Unknown strategy plugin: {plugin_name}") from exc

    def create(
        self, plugin_name: str, strategy_id: str, parameters: dict[str, Any]
    ) -> Strategy:
        """Validate parameters and instantiate one discovered strategy."""

        try:
            strategy_class = self._strategies[plugin_name]
        except KeyError as exc:
            raise PluginError(f"Unknown strategy plugin: {plugin_name}") from exc
        validated = strategy_class.metadata().validate_parameters(parameters)
        return strategy_class.from_parameters(strategy_id, validated)
