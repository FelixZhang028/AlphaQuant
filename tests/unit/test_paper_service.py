from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from quant_platform.application.backtest_service import BacktestRequest
from quant_platform.application.paper_service import PaperTradingService


class _FakeBacktests:
    def __init__(
        self, root: Path, request: BacktestRequest, *, metrics_reliable: bool = True
    ) -> None:
        self.runs_root = root / "runs"
        self.request = request
        self.metrics_reliable = metrics_reliable

    def default_request(self) -> BacktestRequest:
        return self.request

    def run(self, request: BacktestRequest) -> SimpleNamespace:
        return SimpleNamespace(
            result=SimpleNamespace(
                run_id="paper-run",
                summary={"metrics_reliable": self.metrics_reliable},
            )
        )


def test_paper_account_is_persisted_and_advanced(tmp_path: Path) -> None:
    request = BacktestRequest(
        strategy_plugin="fake",
        strategy_id="paper",
        strategy_parameters={"lookback": 20},
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        initial_cash=100_000,
        top_n=5,
        rebalance="weekly",
    )
    service = PaperTradingService(_FakeBacktests(tmp_path, request))  # type: ignore[arg-type]

    account = service.create("测试账户")
    updated = service.advance(account.account_id, date(2024, 6, 30))

    assert service.list_accounts()[0].display_name == "测试账户"
    assert updated.status == "ACTIVE"
    assert updated.last_date == "2024-06-30"
    assert updated.last_run_id == "paper-run"


def test_paper_account_rejects_unreliable_result(tmp_path: Path) -> None:
    request = BacktestRequest(
        strategy_plugin="fake",
        strategy_id="paper",
        strategy_parameters={"lookback": 20},
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        initial_cash=100_000,
        top_n=5,
        rebalance="weekly",
    )
    service = PaperTradingService(
        _FakeBacktests(tmp_path, request, metrics_reliable=False)  # type: ignore[arg-type]
    )
    account = service.create("不可信账户")

    with pytest.raises(ValueError, match="未通过当前可信度审计"):
        service.advance(account.account_id, date(2024, 6, 30))

    assert service.get(account.account_id).status == "FAILED"
