import pytest

from quant_platform.core.exceptions import ConfigurationError
from quant_platform.strategies.discovery import StrategyCatalog


def test_catalog_discovers_strategy_and_validates_parameters() -> None:
    catalog = StrategyCatalog()

    assert "a_share_momentum" in catalog.names()
    metadata = catalog.get_metadata("a_share_momentum")
    strategy = catalog.create(
        "a_share_momentum", "demo", metadata.defaults()
    )

    assert strategy.strategy_id == "demo"
    assert metadata.display_name == "A股动量策略"
    with pytest.raises(ConfigurationError):
        catalog.create(
            "a_share_momentum",
            "bad",
            {**metadata.defaults(), "short_window": -1},
        )
