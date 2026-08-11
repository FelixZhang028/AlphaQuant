from datetime import date
from pathlib import Path

from quant_platform.backtest.engine import BacktestEngine
from quant_platform.execution.next_open import ExecutionConfig, NextOpenExecutionModel
from quant_platform.execution.order_generator import OrderGenerator
from quant_platform.portfolio.equal_weight import EqualWeightPortfolio
from quant_platform.sample_data import generate_sample_market_data
from quant_platform.strategies.momentum import (
    AShareMomentumStrategy,
    MomentumParameters,
)
from quant_platform.universe.a_share import AShareUniverse, AShareUniverseConfig


def test_complete_t_plus_one_backtest(tmp_path: Path) -> None:
    symbols = ["000001.SZ", "000002.SZ", "600000.SH", "600036.SH"]
    repository = generate_sample_market_data(
        tmp_path / "market", symbols, date(2022, 1, 3), date(2023, 12, 29)
    )
    strategy = AShareMomentumStrategy("momentum", MomentumParameters(20, 60, 1.0))
    engine = BacktestEngine(
        repository=repository,
        universe=AShareUniverse(
            AShareUniverseConfig(
                tuple(symbols), minimum_history_days=61, minimum_average_amount=1.0
            )
        ),
        strategy=strategy,
        portfolio=EqualWeightPortfolio(2),
        order_generator=OrderGenerator(100),
        execution_model=NextOpenExecutionModel(ExecutionConfig(slippage_rate=0.0)),
        rebalance="weekly",
    )

    result = engine.run(date(2023, 1, 3), date(2023, 12, 29), 1_000_000)

    assert not result.nav.empty
    assert not result.orders.empty
    assert not result.fills.empty
    assert (result.orders["execution_date"] > result.orders["signal_date"]).all()
    fill_dates = dict(zip(result.fills["order_id"], result.fills["trade_date"], strict=False))
    assert all(
        fill_dates.get(row.order_id) == row.execution_date
        for row in result.orders.itertuples()
        if row.order_id in fill_dates
    )
    assert result.nav["equity"].gt(0).all()


def test_unknown_market_data_produces_diagnostic_only_result(tmp_path: Path) -> None:
    symbols = ["000001.SZ", "000002.SZ", "600000.SH", "600036.SH"]
    repository = generate_sample_market_data(
        tmp_path / "market", symbols, date(2022, 1, 3), date(2023, 12, 29)
    )
    bars = repository.read_table("daily_bars")
    bars["quality_status"] = "UNKNOWN_STATUS"
    repository.save_table("daily_bars", bars)
    engine = BacktestEngine(
        repository=repository,
        universe=AShareUniverse(
            AShareUniverseConfig(
                tuple(symbols), minimum_history_days=61, minimum_average_amount=1.0
            )
        ),
        strategy=AShareMomentumStrategy("momentum", MomentumParameters(20, 60, 1.0)),
        portfolio=EqualWeightPortfolio(2),
        order_generator=OrderGenerator(100),
        execution_model=NextOpenExecutionModel(ExecutionConfig(slippage_rate=0.0)),
        rebalance="weekly",
    )

    result = engine.run(date(2023, 1, 3), date(2023, 12, 29), 1_000_000)

    assert result.fills.empty
    assert result.summary["validity_status"] == "INVALID"
    assert result.summary["metrics_reliable"] is False
    assert result.summary["unknown_market_rows"] > 0
    assert result.validity["blocks_completion"] is False
