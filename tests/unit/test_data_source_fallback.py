import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import yaml

from quant_platform.application.data_service import DataCenterService
from quant_platform.data.quality import DataQualityReport


def _write_yaml(path: Path, value: object) -> None:
    path.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def test_data_center_falls_back_from_ifind_to_akshare(
    tmp_path: Path, monkeypatch: object
) -> None:
    universe_path = tmp_path / "universe.yaml"
    sources_path = tmp_path / "sources.yaml"
    app_path = tmp_path / "app.yaml"
    _write_yaml(universe_path, {"universe": {"symbols": ["000001.SZ"]}})
    _write_yaml(
        sources_path,
        {
            "providers": {
                "ifind": {"enabled": True},
                "akshare": {"enabled": True},
            },
            "routing": {"daily_bars": ["ifind", "akshare"]},
            "quality": {"allow_fallback_provider": True},
        },
    )
    _write_yaml(
        app_path,
        {
            "app": {"runtime_dir": str(tmp_path / "runtime")},
            "data": {
                "repository": str(tmp_path / "market"),
                "source_config": str(sources_path),
            },
            "universe": {"config": str(universe_path)},
            "backtest": {"benchmark": "000300.SH"},
        },
    )
    report = DataQualityReport(1, 0, 0, {}, {"UNKNOWN_STATUS": 1})

    def fail_ifind(*args: object, **kwargs: object) -> DataQualityReport:
        raise ConnectionError("iFinD unavailable")

    def pass_akshare(*args: object, **kwargs: object) -> DataQualityReport:
        return report

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "quant_platform.application.data_service.IFindRangeBackfill.backfill", fail_ifind
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "quant_platform.application.data_service.AkShareRangeBackfill.backfill", pass_akshare
    )
    service = DataCenterService(app_path, client=object(), ifind_client=object())

    source, actual_report, attempts = service._run_market_backfill(
        ["000001.SZ"], date(2024, 1, 2), date(2024, 1, 3)
    )

    assert source == "akshare"
    assert actual_report is report
    assert [attempt["status"] for attempt in attempts] == ["failed", "success"]

    source, _, attempts = service._run_market_backfill(
        ["000001.SZ"],
        date(2024, 1, 2),
        date(2024, 1, 3),
        source_order=["akshare", "ifind"],
        allow_fallback=True,
    )
    assert source == "akshare"
    assert attempts == [{"source": "akshare", "status": "success"}]

    with pytest.raises(ConnectionError, match="iFinD unavailable"):
        service._run_market_backfill(
            ["000001.SZ"],
            date(2024, 1, 2),
            date(2024, 1, 3),
            source_order=["ifind", "akshare"],
            allow_fallback=False,
        )

    assert service._resolve_market_sources(["akshare", "ifind", "akshare"]) == [
        "akshare",
        "ifind",
    ]
    with pytest.raises(ValueError, match="disabled or not routed"):
        service._resolve_market_sources(["unknown"])

    status = service.market_source_status()
    assert list(status["provider"]) == ["ifind", "akshare"]
    assert list(status["role"]) == ["PRIMARY", "FALLBACK"]


def test_manifest_provider_attempts_become_a_readable_route() -> None:
    manifests = pd.DataFrame(
        {
            "parameters_json": [
                json.dumps(
                    {
                        "requested_sources": ["ifind", "akshare"],
                        "fallback_enabled": True,
                        "provider_attempts": [
                            {"source": "ifind", "status": "failed"},
                            {"source": "akshare", "status": "success"},
                        ]
                    }
                )
            ]
        }
    )

    result = DataCenterService._add_provider_route_summary(manifests)

    assert result.iloc[0]["provider_route"] == "ifind:failed -> akshare:success"
    assert bool(result.iloc[0]["fallback_used"])
    assert result.iloc[0]["requested_route"] == "ifind -> akshare"
    assert bool(result.iloc[0]["fallback_enabled"])


def test_data_center_falls_back_when_baostock_is_unavailable(
    tmp_path: Path, monkeypatch: object
) -> None:
    universe_path = tmp_path / "universe.yaml"
    sources_path = tmp_path / "sources.yaml"
    app_path = tmp_path / "app.yaml"
    _write_yaml(universe_path, {"universe": {"symbols": ["000001.SZ"]}})
    _write_yaml(
        sources_path,
        {
            "providers": {
                "baostock": {"enabled": True},
                "akshare": {"enabled": True},
            },
            "routing": {"daily_bars": ["baostock", "akshare"]},
            "quality": {"allow_fallback_provider": True},
        },
    )
    _write_yaml(
        app_path,
        {
            "app": {"runtime_dir": str(tmp_path / "runtime")},
            "data": {
                "repository": str(tmp_path / "market"),
                "source_config": str(sources_path),
            },
            "universe": {"config": str(universe_path)},
            "backtest": {"benchmark": "000300.SH"},
        },
    )
    report = DataQualityReport(1, 0, 0, {}, {"UNKNOWN_STATUS": 1})

    def fail_baostock(*args: object, **kwargs: object) -> DataQualityReport:
        raise ConnectionError("BaoStock unavailable")

    def pass_akshare(*args: object, **kwargs: object) -> DataQualityReport:
        return report

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "quant_platform.application.data_service.BaoStockRangeBackfill.backfill",
        fail_baostock,
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "quant_platform.application.data_service.AkShareRangeBackfill.backfill",
        pass_akshare,
    )
    service = DataCenterService(
        app_path, client=object(), baostock_client=object()
    )

    source, actual_report, attempts = service._run_market_backfill(
        ["000001.SZ"], date(2024, 1, 2), date(2024, 1, 3)
    )

    assert source == "akshare"
    assert actual_report is report
    assert attempts[0]["source"] == "baostock"
    assert attempts[0]["status"] == "failed"
    assert attempts[1] == {"source": "akshare", "status": "success"}
    status = service.market_source_status()
    assert list(status["provider"]) == ["baostock", "akshare"]
    assert list(status["readiness"]) == ["READY", "READY"]
