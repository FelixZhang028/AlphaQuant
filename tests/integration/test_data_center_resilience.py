from pathlib import Path

import pandas as pd
import yaml

from quant_platform.application.data_service import DataCenterService


class PartiallyFailingAkShare:
    def stock_info_a_code_name(self) -> pd.DataFrame:
        return pd.DataFrame({"code": ["000001"], "name": ["平安银行"]})

    def stock_zh_a_hist(self, **parameters: object) -> pd.DataFrame:
        raise ConnectionError("stock endpoint unavailable")

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


def test_one_failed_dataset_does_not_stop_remaining_updates(
    tmp_path: Path, monkeypatch: object
) -> None:
    universe_path = tmp_path / "universe.yaml"
    app_path = tmp_path / "app.yaml"
    _write_yaml(universe_path, {"universe": {"symbols": ["000001.SZ"]}})
    _write_yaml(
        app_path,
        {
            "app": {"runtime_dir": str(tmp_path / "runtime")},
            "data": {"repository": str(tmp_path / "market")},
            "universe": {"config": str(universe_path)},
            "backtest": {"benchmark": "000300.SH"},
        },
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "quant_platform.data.akshare_backfill.time.sleep", lambda _: None
    )
    service = DataCenterService(app_path, client=PartiallyFailingAkShare())

    results = service.update_all(
        pd.Timestamp("2024-01-02").date(), pd.Timestamp("2024-01-03").date()
    )

    assert [result.status for result in results] == ["SUCCESS", "FAILED", "SUCCESS"]
    assert results[1].dataset == "daily_bars"
    assert results[1].error
    assert service.overview().benchmark.rows == 2
