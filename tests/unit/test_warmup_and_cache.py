"""P0-3 测试：warmup 行情加载边界与缓存指纹失效。"""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from quant_platform.backtest.engine import BacktestEngine
from quant_platform.data.versioning import DataManifest, save_manifest
from quant_platform.execution.next_open import ExecutionConfig, NextOpenExecutionModel
from quant_platform.execution.order_generator import OrderGenerator
from quant_platform.portfolio.equal_weight import EqualWeightPortfolio
from quant_platform.sample_data import generate_sample_market_data
from quant_platform.strategies.momentum import AShareMomentumStrategy, MomentumParameters
from quant_platform.universe.a_share import AShareUniverse, AShareUniverseConfig
from quant_platform.web.service_cache import data_fingerprint

SYMBOLS = ["000001.SZ", "000002.SZ", "600000.SH", "600036.SH"]
START = date(2023, 1, 3)
END = date(2023, 6, 30)


class _RecordingRepository:
    """转发仓储调用，记录 get_daily_bars 的股票过滤与加载区间。"""

    def __init__(self, inner):
        self._inner = inner
        self.bars_calls: list[tuple[tuple[str, ...] | None, date | None, date | None]] = []

    def get_daily_bars(self, symbols=None, start_date=None, end_date=None):
        self.bars_calls.append(
            (tuple(symbols) if symbols is not None else None, start_date, end_date)
        )
        return self._inner.get_daily_bars(
            symbols=symbols, start_date=start_date, end_date=end_date
        )

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _make_engine(repository, warmup_days: int) -> BacktestEngine:
    return BacktestEngine(
        repository=repository,
        universe=AShareUniverse(
            AShareUniverseConfig(
                tuple(SYMBOLS), minimum_history_days=61, minimum_average_amount=1.0
            )
        ),
        strategy=AShareMomentumStrategy("momentum", MomentumParameters(20, 60, 1.0)),
        portfolio=EqualWeightPortfolio(2),
        order_generator=OrderGenerator(100),
        execution_model=NextOpenExecutionModel(ExecutionConfig(slippage_rate=0.0)),
        rebalance="weekly",
        warmup_days=warmup_days,
    )


def test_zero_warmup_loads_only_requested_window(tmp_path: Path) -> None:
    repository = generate_sample_market_data(
        tmp_path / "market", SYMBOLS, date(2022, 6, 1), END
    )
    spy = _RecordingRepository(repository)

    _make_engine(spy, warmup_days=0).run(START, END, 1_000_000)

    # 单次调用、只加载股票池 × [start, end]，不回看不必要的历史。
    assert len(spy.bars_calls) == 1
    symbols, start_date, end_date = spy.bars_calls[0]
    assert symbols == tuple(SYMBOLS)
    assert start_date == START
    assert end_date == END


def test_warmup_loads_exactly_trading_days_back(tmp_path: Path) -> None:
    repository = generate_sample_market_data(
        tmp_path / "market", SYMBOLS, date(2022, 6, 1), END
    )
    spy = _RecordingRepository(repository)

    _make_engine(spy, warmup_days=10).run(START, END, 1_000_000)

    _, start_date, end_date = spy.bars_calls[0]
    calendar = repository.get_trade_calendar(
        START - timedelta(days=400), START - timedelta(days=1)
    )
    trading_days = [ts.date() for ts in pd.to_datetime(calendar["cal_date"])]
    # 按交易日历回推 10 个交易日，而不是日历日近似。
    assert start_date == trading_days[-10]
    assert end_date == END


def test_warmup_exceeding_available_history_falls_back_to_earliest(tmp_path: Path) -> None:
    # 本地数据只有 2022-12-01 起：warmup 120 > 可用历史 → 从最早交易日加载。
    repository = generate_sample_market_data(
        tmp_path / "market", SYMBOLS, date(2022, 12, 1), END
    )
    spy = _RecordingRepository(repository)

    _make_engine(spy, warmup_days=120).run(START, END, 1_000_000)

    _, start_date, _ = spy.bars_calls[0]
    assert start_date == date(2022, 12, 1)


def test_fingerprint_without_manifests_uses_sentinel(tmp_path: Path) -> None:
    repository = generate_sample_market_data(
        tmp_path / "market", SYMBOLS, date(2022, 6, 1), END
    )

    assert data_fingerprint(repository) == "no-successful-manifest"


def test_fingerprint_tracks_latest_success_manifests(tmp_path: Path) -> None:
    repository = generate_sample_market_data(
        tmp_path / "market", SYMBOLS, date(2022, 6, 1), END
    )
    save_manifest(
        repository,
        DataManifest.start("daily_bars", "synthetic", {}).succeed(
            row_count=10, symbol_count=2
        ),
    )
    save_manifest(
        repository,
        DataManifest.start("benchmark_bars", "synthetic", {}).succeed(
            row_count=5, symbol_count=1
        ),
    )

    fingerprint = data_fingerprint(repository)
    assert "daily_bars:" in fingerprint
    assert "benchmark_bars:" in fingerprint

    # 新版本成功入库后指纹变化，缓存随之失效。
    save_manifest(
        repository,
        DataManifest.start("daily_bars", "synthetic", {}).succeed(
            row_count=20, symbol_count=4
        ),
    )
    assert data_fingerprint(repository) != fingerprint


def test_failed_manifests_do_not_change_fingerprint(tmp_path: Path) -> None:
    repository = generate_sample_market_data(
        tmp_path / "market", SYMBOLS, date(2022, 6, 1), END
    )
    save_manifest(
        repository,
        DataManifest.start("daily_bars", "synthetic", {}).fail(ValueError("boom")),
    )

    # 只有成功版本参与指纹：失败版本不产生缓存失效信号。
    assert data_fingerprint(repository) == "no-successful-manifest"
