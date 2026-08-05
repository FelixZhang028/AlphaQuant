from __future__ import annotations

from pathlib import Path

import yaml

from quant_platform.application.universe_service import (
    UniverseManagementService,
    normalize_a_share_symbol,
    parse_symbol_text,
    update_universe_settings,
)


def _write_yaml(path: Path, value: object) -> None:
    path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_symbol_normalization_accepts_common_user_inputs() -> None:
    assert normalize_a_share_symbol("600519") == "600519.SH"
    assert normalize_a_share_symbol("sz000001") == "000001.SZ"
    assert normalize_a_share_symbol("300750.sz") == "300750.SZ"
    assert parse_symbol_text("600519，000001\n600519.SH") == ("600519.SH", "000001.SZ")


def test_universe_service_adds_removes_and_preserves_custom_config(tmp_path: Path) -> None:
    universe_path = tmp_path / "universe.yaml"
    app_path = tmp_path / "app.yaml"
    _write_yaml(
        universe_path,
        {
            "universe": {
                "id": "personal",
                "symbols": ["000001.SZ"],
                "custom_key": "keep-me",
                "filters": {"exclude_st": True, "minimum_history_days": 61},
            }
        },
    )
    _write_yaml(
        app_path,
        {
            "data": {"repository": str(tmp_path / "market")},
            "universe": {"config": str(universe_path)},
        },
    )

    service = UniverseManagementService(app_path)
    service.add_symbols("600519, 300750")
    current = service.load()
    service.save(update_universe_settings(current, minimum_average_amount=12_000_000.0))
    updated = service.remove_symbols(["600519.SH"])
    raw = yaml.safe_load(universe_path.read_text(encoding="utf-8"))

    assert updated.symbols == ("000001.SZ", "300750.SZ")
    assert raw["universe"]["custom_key"] == "keep-me"
    assert raw["universe"]["filters"]["minimum_average_amount"] == 12_000_000.0
