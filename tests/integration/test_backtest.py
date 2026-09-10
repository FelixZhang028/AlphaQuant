from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from quant_platform.backtest.diagnosis import generate_diagnosis
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


def _make_engine(repository, symbols: list[str], **overrides) -> BacktestEngine:
    """Build the standard demo engine, allowing keyword overrides."""

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
    for key, value in overrides.items():
        setattr(engine, key, value)
    return engine


def test_complete_t_plus_one_backtest(tmp_path: Path) -> None:
    symbols = ["000001.SZ", "000002.SZ", "600000.SH", "600036.SH"]
    repository = generate_sample_market_data(
        tmp_path / "market", symbols, date(2022, 1, 3), date(2023, 12, 29)
    )
    engine = _make_engine(repository, symbols)

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
    engine = _make_engine(repository, symbols)

    result = engine.run(date(2023, 1, 3), date(2023, 12, 29), 1_000_000)

    assert result.fills.empty
    assert result.summary["validity_status"] == "INVALID"
    assert result.summary["metrics_reliable"] is False
    assert result.summary["unknown_market_rows"] > 0
    assert result.validity["blocks_completion"] is False


def _save_benchmark(repository, symbol: str, start: date, end: date) -> tuple[pd.DataFrame, list[float]]:
    """Persist a deterministic benchmark index and return (dates, closes)."""

    bench_dates = pd.bdate_range(start, end)
    closes = [100.0 + 0.5 * index for index in range(len(bench_dates))]
    frame = pd.DataFrame(
        {
            "symbol": symbol,
            "trade_date": bench_dates,
            "raw_open": closes,
            "raw_high": closes,
            "raw_low": closes,
            "raw_close": closes,
            "volume": 1_000_000,
            "amount": 1_000_000.0,
            "source": "synthetic",
            "quality_status": "OK",
        }
    )
    # 挖掉两根中间行情，验证基准当日无数据时的前向填充。
    gapped = frame[
        ~frame["trade_date"].isin([bench_dates[30], bench_dates[31]])
    ].reset_index(drop=True)
    repository.save_table("benchmark_bars", gapped)
    return bench_dates, closes


def test_benchmark_equity_tracks_configured_index(tmp_path: Path) -> None:
    symbols = ["000001.SZ", "000002.SZ", "600000.SH", "600036.SH"]
    repository = generate_sample_market_data(
        tmp_path / "market", symbols, date(2022, 1, 3), date(2023, 12, 29)
    )
    bench_dates, closes = _save_benchmark(
        repository, "000300.SH", date(2023, 1, 3), date(2023, 12, 29)
    )
    engine = _make_engine(repository, symbols, benchmark_symbol="000300.SH")

    result = engine.run(date(2023, 1, 3), date(2023, 12, 29), 1_000_000)

    assert "benchmark_equity" in result.nav.columns
    bench = pd.to_numeric(result.nav["benchmark_equity"], errors="coerce")
    assert bench.notna().all()
    assert bench.iloc[0] == pytest.approx(1_000_000.0)
    assert bench.iloc[-1] == pytest.approx(1_000_000.0 * closes[-1] / closes[0])
    # 缺失两日沿用前一交易日基准净值（前向填充）。
    assert bench.iloc[30] == pytest.approx(bench.iloc[29])
    assert bench.iloc[31] == pytest.approx(bench.iloc[29])

    expected_return = closes[-1] / closes[0] - 1.0
    assert result.summary["benchmark_symbol"] == "000300.SH"
    assert result.summary["benchmark_return"] == pytest.approx(expected_return)
    assert result.summary["excess_return"] == pytest.approx(
        result.summary["cumulative_return"] - expected_return
    )

    section = next(
        item for item in generate_diagnosis(result).sections if item.title == "与沪深300对比"
    )
    assert not any("未配置" in bullet for bullet in section.bullets)
    assert any("跑赢" in bullet or "跑输" in bullet for bullet in section.bullets)
    assert len(bench_dates) == len(bench)


def test_backtest_without_benchmark_omits_column(tmp_path: Path) -> None:
    symbols = ["000001.SZ", "000002.SZ", "600000.SH", "600036.SH"]
    repository = generate_sample_market_data(
        tmp_path / "market", symbols, date(2022, 1, 3), date(2023, 12, 29)
    )
    engine = _make_engine(repository, symbols)

    result = engine.run(date(2023, 1, 3), date(2023, 12, 29), 1_000_000)

    assert "benchmark_equity" not in result.nav.columns
    assert "benchmark_return" not in result.summary
    assert "excess_return" not in result.summary


def test_benchmark_configured_without_data_degrades_to_na_column(tmp_path: Path) -> None:
    symbols = ["000001.SZ", "000002.SZ", "600000.SH", "600036.SH"]
    repository = generate_sample_market_data(
        tmp_path / "market", symbols, date(2022, 1, 3), date(2023, 12, 29)
    )
    engine = _make_engine(repository, symbols, benchmark_symbol="000300.SH")

    result = engine.run(date(2023, 1, 3), date(2023, 12, 29), 1_000_000)

    assert "benchmark_equity" in result.nav.columns
    assert pd.to_numeric(result.nav["benchmark_equity"], errors="coerce").isna().all()
    assert result.summary.get("benchmark_symbol") == "000300.SH"
    assert "benchmark_return" not in result.summary

    section = next(
        item for item in generate_diagnosis(result).sections if item.title == "与沪深300对比"
    )
    assert any("未配置" in bullet for bullet in section.bullets)
