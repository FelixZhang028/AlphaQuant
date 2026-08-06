from datetime import date
from pathlib import Path

import yaml

from quant_platform.application.backtest_service import BacktestService
from quant_platform.sample_data import generate_sample_market_data


def _write_yaml(path: Path, value: object) -> None:
    path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_service_runs_discovered_strategy_and_saves_snapshot(tmp_path: Path) -> None:
    symbols = ["000001.SZ", "000002.SZ", "600000.SH", "600036.SH"]
    market = tmp_path / "market"
    generate_sample_market_data(market, symbols, date(2022, 1, 3), date(2023, 12, 29))
    universe_path = tmp_path / "universe.yaml"
    strategy_path = tmp_path / "strategy.yaml"
    execution_path = tmp_path / "execution.yaml"
    app_path = tmp_path / "app.yaml"
    _write_yaml(
        universe_path,
        {
            "universe": {
                "symbols": symbols,
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
                "id": "service_test",
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
    _write_yaml(
        execution_path,
        {
            "execution": {
                "lot_size": 100,
                "commission_rate": 0.0003,
                "minimum_commission": 5,
                "stamp_tax_rate": 0.0005,
                "slippage_rate": 0,
                "unknown_status_policy": "reject_trade",
            }
        },
    )
    _write_yaml(
        app_path,
        {
            "app": {"runtime_dir": str(tmp_path / "runtime")},
            "data": {"repository": str(market)},
            "universe": {"config": str(universe_path)},
            "strategy": {"config": str(strategy_path)},
            "portfolio": {"plugin": "equal_weight", "top_n": 2},
            "execution": {"config": str(execution_path)},
            "backtest": {
                "start_date": "2023-01-03",
                "end_date": "2023-12-29",
                "initial_cash": 1_000_000,
            },
        },
    )

    service = BacktestService(app_path)
    completed = service.run()

    assert "a_share_momentum" in {item.plugin_name for item in service.available_strategies()}
    assert not completed.result.nav.empty
    assert completed.output_dir.exists()
    assert (completed.output_dir / "config.snapshot.yaml").exists()
    assert (completed.output_dir / "validity_report.json").exists()
    assert completed.result.summary["validity_status"] == "WARNING"
    assert completed.result.summary["metrics_reliable"] is True
    assert "DAILY_POSITION" in set(completed.result.risk_events["event_type"])
