"""Built-in non-strategy plugin registration."""

from __future__ import annotations

from quant_platform.core.registry import PluginRegistry
from quant_platform.portfolio.equal_weight import EqualWeightPortfolio


def default_registry() -> PluginRegistry:
    """Return built-in platform plugins.

    Strategies are discovered automatically by ``StrategyCatalog`` and are
    deliberately absent from this manual registry.
    """

    registry = PluginRegistry()
    registry.register(
        "portfolio",
        "equal_weight",
        lambda *, top_n: EqualWeightPortfolio(top_n=int(top_n)),
    )
    return registry
