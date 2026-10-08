"""Strategy interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from quant_platform.signals.models import Signal
from quant_platform.strategies.context import StrategyContext
from quant_platform.strategies.spec import StrategyMetadata, StrategyParameter


class Strategy(ABC):
    """Generate signals without depending on storage or execution details."""

    plugin_name: ClassVar[str]
    display_name: ClassVar[str]
    description: ClassVar[str] = ""
    parameters: ClassVar[tuple[StrategyParameter, ...]] = ()
    required_fields: ClassVar[frozenset[str]] = frozenset()
    strategy_id: str

    @classmethod
    def metadata(cls) -> StrategyMetadata:
        """Return metadata used for discovery, validation, and web forms."""

        return StrategyMetadata(
            plugin_name=cls.plugin_name,
            display_name=cls.display_name,
            description=cls.description,
            parameters=cls.parameters,
            required_fields=cls.required_fields,
        )

    @classmethod
    @abstractmethod
    def from_parameters(cls, strategy_id: str, parameters: dict[str, Any]) -> Strategy:
        """Build a strategy from values validated against its metadata."""

    @abstractmethod
    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        """Generate scored signals using the supplied point-in-time context."""
