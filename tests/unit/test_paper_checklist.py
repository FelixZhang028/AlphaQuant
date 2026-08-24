from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
import yaml

from quant_platform.application.backtest_service import BacktestRequest
from quant_platform.application.paper_checklist import evaluate_go_live_checklist
from quant_platform.application.paper_service import PaperTradingService
from quant_platform.backtest.run_store import BacktestRunStore
from quant_platform.backtest.validity import CURRENT_AUDIT_VERSION
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository


class _FakeBacktests:
    def __init__(self, root: Path, request: BacktestRequest, repository_root: Path) -> None:
        self.runs_root = root / "runs"
        self.request = request
        self.configs: dict[str, Any] = {"app": {"data": {"repository": str(repository_root)}}}

    @property
    def run_store(self) -> BacktestRunStore:
        return BacktestRunStore(self.runs_root)

    def default_request(self) -> BacktestRequest:
        return self.request

    def run(self, request: BacktestRequest) -> SimpleNamespace:
        return SimpleNamespace(
            result=SimpleNamespace(
                run_id="paper-run",
                summary={"metrics_reliable": True},
            )
        )


def _request() -> BacktestRequest:
    return BacktestRequest(
        strategy_plugin="fake",
        strategy_id="paper",
        strategy_parameters={"lookback": 20},
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        initial_cash=100_000,
        top_n=5,
        rebalance="weekly",
    )


def _write_validity(run_dir: Path, *, reliable: bool = True) -> None:
    (run_dir / "validity_report.json").write_text(
        json.dumps(
            {
                "status": "VALID" if reliable else "INVALID",
                "metrics_reliable": reliable,
                "issues": [],
                "audit_version": CURRENT_AUDIT_VERSION,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _seed_repository(
    root: Path, latest: date, *, calendar_through: date
) -> ParquetMarketDataRepository:
    repository = ParquetMarketDataRepository(root)
    repository.save_table(
        "daily_bars",
        pd.DataFrame(
            {"symbol": ["000001.SZ"], "trade_date": [latest.isoformat()], "close": [10.0]}
        ),
    )
    span = (calendar_through - latest).days + 1
    days = [latest + timedelta(days=offset) for offset in range(span)]
    repository.save_table(
        "trade_calendar",
        pd.DataFrame({"cal_date": [day.isoformat() for day in days], "is_open": [1] * len(days)}),
    )
    return repository


def _seed_oos_run(runs_root: Path, plugin: str = "fake") -> None:
    run_dir = runs_root / "oos-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": "oos-run",
                "status": "SUCCESS",
                "created_at": "2024-01-01T00:00:00+00:00",
                "updated_at": "2024-01-01T00:00:00+00:00",
                "strategy_plugin": plugin,
                "strategy_id": "paper_wf_test",
                "start_date": "2024-01-01",
                "end_date": "2024-06-30",
                "run_kind": "walk_forward_oos",
                "error": None,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    (run_dir / "config.snapshot.yaml").write_text(
        yaml.safe_dump({"app": {"backtest": {"evaluation_mode": "out_of_sample"}}}),
        encoding="utf-8",
    )
    _write_validity(run_dir)


def _build_service(tmp_path: Path) -> tuple[PaperTradingService, ParquetMarketDataRepository]:
    repository = _seed_repository(tmp_path / "data", date.today(), calendar_through=date.today())
    service = PaperTradingService(_FakeBacktests(tmp_path, _request(), tmp_path / "data"))  # type: ignore[arg-type]
    return service, repository


def _advance_and_seed_run(service: PaperTradingService, account_id: str) -> None:
    service.advance(account_id, date(2024, 6, 30))
    run_dir = service.backtests.runs_root / "paper-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    _write_validity(run_dir)


def test_checklist_passes_when_everything_ready(tmp_path: Path) -> None:
    service, repository = _build_service(tmp_path)
    account = service.create("测试账户")
    _seed_oos_run(service.backtests.runs_root)
    _advance_and_seed_run(service, account.account_id)

    report = evaluate_go_live_checklist(
        service, account.account_id, repository=repository, today=date.today()
    )

    assert not report.blocked
    assert all(item.passed for item in report.items)


def test_checklist_blocks_on_stale_data(tmp_path: Path) -> None:
    service, _ = _build_service(tmp_path)
    account = service.create("测试账户")
    _advance_and_seed_run(service, account.account_id)
    stale = date.today() - timedelta(days=10)
    repository = _seed_repository(
        tmp_path / "stale_data", stale, calendar_through=date.today()
    )

    report = evaluate_go_live_checklist(
        service, account.account_id, repository=repository, today=date.today()
    )

    item = report.by_key("data_freshness")
    assert report.blocked
    assert not item.passed
    assert item.severity == "blocker"


def test_checklist_warns_on_slightly_stale_data(tmp_path: Path) -> None:
    service, _ = _build_service(tmp_path)
    account = service.create("测试账户")
    _advance_and_seed_run(service, account.account_id)
    recent = date.today() - timedelta(days=2)
    repository = _seed_repository(
        tmp_path / "recent_data", recent, calendar_through=date.today()
    )

    report = evaluate_go_live_checklist(
        service, account.account_id, repository=repository, today=date.today()
    )

    item = report.by_key("data_freshness")
    assert not item.passed
    assert item.severity == "warning"
    assert not report.blocked


def test_checklist_blocks_on_missing_risk_limits(tmp_path: Path) -> None:
    service, repository = _build_service(tmp_path)
    account = service.create("测试账户")
    _advance_and_seed_run(service, account.account_id)
    broken = dict(account.request)
    broken["risk_limits"] = {}
    service._write(replace(account, request=broken))

    report = evaluate_go_live_checklist(
        service, account.account_id, repository=repository, today=date.today()
    )

    item = report.by_key("risk_limits")
    assert report.blocked
    assert not item.passed
    assert item.severity == "blocker"


def test_checklist_blocks_without_any_run(tmp_path: Path) -> None:
    service, repository = _build_service(tmp_path)
    account = service.create("测试账户")

    report = evaluate_go_live_checklist(
        service, account.account_id, repository=repository, today=date.today()
    )

    item = report.by_key("latest_run")
    assert report.blocked
    assert not item.passed
    assert item.severity == "blocker"


def test_checklist_warns_without_out_of_sample_record(tmp_path: Path) -> None:
    service, repository = _build_service(tmp_path)
    account = service.create("测试账户")
    _advance_and_seed_run(service, account.account_id)

    report = evaluate_go_live_checklist(
        service, account.account_id, repository=repository, today=date.today()
    )

    item = report.by_key("out_of_sample")
    assert not item.passed
    assert item.severity == "warning"
    assert "未找到样本外验证记录" in item.detail


def test_service_go_live_checklist_uses_configured_repository(tmp_path: Path) -> None:
    service, _ = _build_service(tmp_path)
    account = service.create("测试账户")
    _seed_oos_run(service.backtests.runs_root)
    _advance_and_seed_run(service, account.account_id)

    report = service.go_live_checklist(account.account_id)

    assert not report.blocked
    assert all(item.passed for item in report.items)


def test_checklist_blocks_on_unreliable_latest_run(tmp_path: Path) -> None:
    service, repository = _build_service(tmp_path)
    account = service.create("测试账户")
    _advance_and_seed_run(service, account.account_id)
    _write_validity(service.backtests.runs_root / "paper-run", reliable=False)

    report = evaluate_go_live_checklist(
        service, account.account_id, repository=repository, today=date.today()
    )

    item = report.by_key("latest_run")
    assert report.blocked
    assert not item.passed


def test_checklist_warns_on_parameter_drift(tmp_path: Path) -> None:
    service, repository = _build_service(tmp_path)
    account = service.create(
        "漂移账户", replace(_request(), strategy_parameters={"lookback": 99})
    )
    _advance_and_seed_run(service, account.account_id)

    report = evaluate_go_live_checklist(
        service, account.account_id, repository=repository, today=date.today()
    )

    item = report.by_key("version_pinning")
    assert not item.passed
    assert item.severity == "warning"
    assert "策略参数" in item.detail


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
