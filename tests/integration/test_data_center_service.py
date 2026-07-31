from pathlib import Path

import pandas as pd
import yaml

from quant_platform.application.data_service import DataCenterService


class FakeAkShareDataCenter:
    def stock_info_a_code_name(self) -> pd.DataFrame:
        return pd.DataFrame({"code": ["000001", "600000"], "name": ["平安银行", "浦发银行"]})

    def stock_zh_a_hist(self, **parameters: object) -> pd.DataFrame:
        adjusted = parameters["adjust"] == "qfq"
        close = [9.5, 10.5] if adjusted else [10.0, 11.0]
        return pd.DataFrame(
            {
                "日期": ["2024-01-02", "2024-01-03"],
                "股票代码": ["000001", "000001"],
                "开盘": [9.9, 10.2],
                "收盘": close,
                "最高": [10.1, 11.2],
                "最低": [9.8, 10.1],
                "成交量": [1000, 1200],
                "成交额": [1_000_000, 1_200_000],
            }
        )

    def index_zh_a_hist(self, **parameters: object) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "日期": ["2024-01-02", "2024-01-03"],
                "开盘": [3300.0, 3310.0],
                "收盘": [3305.0, 3320.0],
                "最高": [3310.0, 3325.0],
                "最低": [3290.0, 3300.0],
                "成交量": [100_000, 110_000],
                "成交额": [1_000_000_000, 1_100_000_000],
            }
        )


def _write_yaml(path: Path, value: object) -> None:
    path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_data_center_updates_versions_and_reports_coverage(tmp_path: Path) -> None:
    universe_path = tmp_path / "universe.yaml"
    app_path = tmp_path / "app.yaml"
    _write_yaml(
        universe_path,
        {"universe": {"symbols": ["000001.SZ"], "filters": {}}},
    )
    _write_yaml(
        app_path,
        {
            "app": {"runtime_dir": str(tmp_path / "runtime")},
            "data": {"repository": str(tmp_path / "market")},
            "universe": {"config": str(universe_path)},
            "backtest": {"benchmark": "000300.SH"},
        },
    )
    service = DataCenterService(app_path, client=FakeAkShareDataCenter())

    results = service.update_all(
        pd.Timestamp("2024-01-02").date(), pd.Timestamp("2024-01-03").date()
    )
    overview = service.overview()

    assert [result.dataset for result in results] == [
        "security_master",
        "daily_bars",
        "benchmark_bars",
    ]
    assert all(result.status == "SUCCESS" for result in results)
    assert overview.security_count == 2
    assert overview.market.coverage_ratio == 1.0
    assert overview.market.unknown_status_rows == 2
    assert overview.benchmark.coverage_ratio == 1.0
    assert len(overview.manifests) == 3
    master = overview.security_master.set_index("symbol")
    assert master.loc["000001.SZ", "name"] == "平安银行"
    assert set(overview.benchmark_bars["symbol"]) == {"000300.SH"}
