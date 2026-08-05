from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from quant_platform.application.readiness_service import (
    PlatformReadinessService,
    platform_needs_onboarding,
)
from quant_platform.sample_data import generate_sample_market_data


def _write_yaml(path: Path, value: object) -> None:
    path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _build_config(tmp_path: Path) -> tuple[Path, Path]:
    market = tmp_path / "market"
    universe_path = tmp_path / "universe.yaml"
    strategy_path = tmp_path / "strategy.yaml"
    execution_path = tmp_path / "execution.yaml"
    app_path = tmp_path / "app.yaml"
    _write_yaml(
        universe_path,
        {
            "universe": {
                "symbols": ["000001.SZ"],
                "filters": {
                    "minimum_listing_days": 61,
                    "minimum_history_days": 61,
                    "minimum_average_amount": 1,
                },
            }
        },
    )
    _write_yaml(
        strategy_path,
        {
            "strategy": {
                "id": "readiness_test",
                "plugin": "a_share_momentum",
                "rebalance": "weekly",
                "parameters": {
                    "short_window": 20,
                    "long_window": 60,
                    "minimum_average_amount": 1,
                },
            }
        },
    )
    _write_yaml(execution_path, {"execution": {"unknown_status_policy": "allow_trade"}})
    _write_yaml(
        app_path,
        {
            "app": {"runtime_dir": str(tmp_path / "runtime")},
            "data": {"repository": str(market)},
            "universe": {"config": str(universe_path)},
            "strategy": {"config": str(strategy_path)},
            "portfolio": {"plugin": "equal_weight", "top_n": 1},
            "execution": {"config": str(execution_path)},
            "backtest": {
                "start_date": "2023-01-03",
                "end_date": "2023-12-29",
                "initial_cash": 1_000_000,
                "benchmark": "000300.SH",
            },
        },
    )
    return app_path, market


def test_readiness_requires_sufficient_local_history(tmp_path: Path) -> None:
    app_path, market = _build_config(tmp_path)
    service = PlatformReadinessService(app_path)

    assert not service.inspect().ready_for_backtest
    assert platform_needs_onboarding(app_path)

    generate_sample_market_data(
        market,
        ["000001.SZ"],
        date(2023, 1, 3),
        date(2023, 6, 30),
    )
    report = service.inspect()

    assert report.ready_for_backtest
    assert not platform_needs_onboarding(app_path)
    assert report.symbols_with_sufficient_history == 1
    assert list(report.to_frame().columns) == ["检查项目", "状态", "说明"]
