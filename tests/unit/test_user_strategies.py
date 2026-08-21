"""Tests for the advanced user strategy base class, loader, and store."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from quant_platform.core.exceptions import ConfigurationError, PluginError
from quant_platform.strategies.context import StrategyContext
from quant_platform.strategies.discovery import StrategyCatalog
from quant_platform.user_strategies import register_strategy
from quant_platform.user_strategies.loader import UserStrategyLoader
from quant_platform.user_strategies.store import UserStrategyStore

SOURCE = '''
from quant_platform.signals.models import Signal
from quant_platform.user_strategies import BaseStrategy, register_strategy


@register_strategy("my_test", display_name="测试策略", description="demo")
class MyTest(BaseStrategy):
    param_specs = {"lookback": {"label": "窗口", "min": 2, "max": 100}}

    def __init__(self, lookback: int = 20, threshold: float = 0.05):
        self.lookback = lookback
        self.threshold = threshold

    def generate_signals(self, context):
        return [
            Signal(self.strategy_id, context.trade_date, symbol, "TEST", 1.0)
            for symbol in context.universe
        ]
'''


def test_loader_registers_and_introspects_parameters() -> None:
    result = UserStrategyLoader().load_source(SOURCE)

    assert not result.errors
    assert set(result.strategies) == {"my_test"}
    metadata = result.strategies["my_test"].metadata()
    assert metadata.display_name == "测试策略"
    assert [parameter.name for parameter in metadata.parameters] == ["lookback", "threshold"]
    assert metadata.parameters[0].kind.value == "integer"
    assert metadata.parameters[1].kind.value == "number"
    assert metadata.parameters[0].minimum == 2
    assert metadata.parameters[0].maximum == 100


def test_loader_instantiates_with_custom_parameters() -> None:
    cls = UserStrategyLoader().load_source(SOURCE).strategies["my_test"]

    strategy = cls.from_parameters("run1", {"lookback": 30, "threshold": 0.1})

    assert strategy.strategy_id == "run1"
    assert strategy.lookback == 30
    assert strategy.threshold == 0.1
    context = StrategyContext.create(
        date(2024, 1, 31),
        pd.DataFrame(columns=["symbol", "trade_date", "adjusted_close"]),
        [],
    )
    assert strategy.generate_signals(context) == []


def test_loader_blocks_forbidden_import() -> None:
    bad_source = (
        "import os\n"
        "from quant_platform.user_strategies import BaseStrategy, register_strategy\n"
        "\n"
        "\n"
        "@register_strategy('bad')\n"
        "class Bad(BaseStrategy):\n"
        "    def generate_signals(self, context):\n"
        "        return []\n"
    )

    result = UserStrategyLoader().load_source(bad_source)

    assert not result.strategies
    assert result.errors
    assert "os" in result.errors[0][1]


def test_loader_rejects_duplicate_registration() -> None:
    duplicate_source = (
        "from quant_platform.user_strategies import BaseStrategy, register_strategy\n"
        "\n"
        "\n"
        "@register_strategy('dup')\n"
        "class A(BaseStrategy):\n"
        "    def generate_signals(self, context):\n"
        "        return []\n"
        "\n"
        "\n"
        "@register_strategy('dup')\n"
        "class B(BaseStrategy):\n"
        "    def generate_signals(self, context):\n"
        "        return []\n"
    )

    result = UserStrategyLoader().load_source(duplicate_source)

    assert not result.strategies
    assert result.errors


def test_loader_requires_parameter_defaults() -> None:
    missing_default = (
        "from quant_platform.user_strategies import BaseStrategy, register_strategy\n"
        "\n"
        "\n"
        "@register_strategy('no_default')\n"
        "class NoDefault(BaseStrategy):\n"
        "    def __init__(self, lookback):\n"
        "        self.lookback = lookback\n"
        "\n"
        "    def generate_signals(self, context):\n"
        "        return []\n"
    )

    result = UserStrategyLoader().load_source(missing_default)

    assert not result.strategies
    assert result.errors
    assert "默认值" in result.errors[0][1]


def test_loader_rejects_invalid_name() -> None:
    bad_name = (
        "from quant_platform.user_strategies import BaseStrategy, register_strategy\n"
        "\n"
        "\n"
        "@register_strategy('bad-name')\n"
        "class Bad(BaseStrategy):\n"
        "    def generate_signals(self, context):\n"
        "        return []\n"
    )

    result = UserStrategyLoader().load_source(bad_name)

    assert not result.strategies
    assert result.errors
    assert "不合法" in result.errors[0][1]


def test_store_saves_lists_and_deletes(tmp_path: Path) -> None:
    store = UserStrategyStore(tmp_path / "user_strategies")

    record = store.save(
        SOURCE,
        plugin_name="my_test",
        display_name="测试",
        description="demo",
        source="upload",
    )
    listed = store.list()

    assert record.plugin_name == "my_test"
    assert len(listed) == 1
    assert listed[0].plugin_name == "my_test"
    assert store.get("my_test") is not None
    store.delete("my_test")
    assert store.list() == ()


def test_store_rejects_invalid_plugin_name(tmp_path: Path) -> None:
    store = UserStrategyStore(tmp_path / "user_strategies")

    with pytest.raises(ConfigurationError):
        store.save(
            SOURCE,
            plugin_name="bad-name",
            display_name="x",
            description="",
            source="editor",
        )


def test_catalog_accepts_user_strategies() -> None:
    catalog = StrategyCatalog()
    result = UserStrategyLoader().load_source(SOURCE)

    catalog.register_classes(result.strategies)

    assert "my_test" in catalog.names()
    strategy = catalog.create("my_test", "run9", {"lookback": 10, "threshold": 0.2})
    assert strategy.lookback == 10
    assert strategy.threshold == 0.2


def test_register_strategy_rejects_non_base_subclass() -> None:
    from quant_platform.user_strategies.base import _clear_user_registry

    _clear_user_registry()
    try:
        with pytest.raises(PluginError):
            register_strategy("not_base")(object)
    finally:
        _clear_user_registry()
