from __future__ import annotations

from pathlib import Path

from quant_platform.application.strategy_studio_service import StrategyPackageStore
from quant_platform.strategies.templates import beginner_templates


def test_strategy_package_store_saves_lists_loads_and_copies(tmp_path: Path) -> None:
    store = StrategyPackageStore(tmp_path / "strategies")
    preset = beginner_templates()[0].presets["balanced"]

    saved = store.save(
        preset.definition,
        top_n=preset.top_n,
        rebalance=preset.rebalance,
    )
    loaded = store.load(saved.package_id)
    copied = store.copy(saved.package_id)

    assert loaded.definition == preset.definition
    assert copied.package_id != saved.package_id
    assert copied.name.endswith("（副本）")
    assert len(store.list()) == 2
