import pytest

from quant_platform.core.exceptions import PluginError
from quant_platform.core.registry import PluginRegistry


def test_registry_creates_plugins_and_rejects_duplicates() -> None:
    registry = PluginRegistry()
    registry.register("strategy", "demo", lambda value: {"value": value})

    assert registry.create("strategy", "demo", value=3) == {"value": 3}
    with pytest.raises(PluginError):
        registry.register("strategy", "demo", dict)
