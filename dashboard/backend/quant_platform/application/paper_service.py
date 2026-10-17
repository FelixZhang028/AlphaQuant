"""Persistent end-of-day paper accounts backed by reproducible replay runs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from quant_platform.application.backtest_service import BacktestRequest, BacktestService
from quant_platform.risk.config import RiskLimits

if TYPE_CHECKING:
    from quant_platform.application.paper_checklist import GoLiveChecklist


@dataclass(frozen=True)
class PaperAccountRecord:
    """Durable configuration and latest result pointer for one paper account."""

    account_id: str
    display_name: str
    status: str
    created_at: str
    updated_at: str
    last_date: str | None
    last_run_id: str | None
    error: str | None
    request: dict[str, Any]


class PaperTradingService:
    """Advance daily paper accounts by replaying their pinned configuration."""

    def __init__(self, backtests: BacktestService) -> None:
        self.backtests = backtests
        self.root = backtests.runs_root.parent / "paper_accounts"

    def create(
        self, display_name: str, request: BacktestRequest | None = None
    ) -> PaperAccountRecord:
        """Create a persistent account without placing any order."""

        name = display_name.strip()
        if not name:
            raise ValueError("模拟账户名称不能为空")
        effective = request or self.backtests.default_request()
        account_id = uuid4().hex[:12]
        now = datetime.now(UTC).isoformat()
        record = PaperAccountRecord(
            account_id=account_id,
            display_name=name,
            status="READY",
            created_at=now,
            updated_at=now,
            last_date=None,
            last_run_id=None,
            error=None,
            request=self._serialize_request(effective),
        )
        self._write(record)
        return record

    def list_accounts(self) -> list[PaperAccountRecord]:
        """Return newest-updated accounts first."""

        if not self.root.exists():
            return []
        records = [self._read(path.parent.name) for path in self.root.glob("*/account.json")]
        return sorted(records, key=lambda item: item.updated_at, reverse=True)

    def get(self, account_id: str) -> PaperAccountRecord:
        """Load one paper account."""

        return self._read(account_id)

    def advance(self, account_id: str, end_date: date) -> PaperAccountRecord:
        """Rebuild the account deterministically through the requested date."""

        current = self.get(account_id)
        request = self._deserialize_request(current.request)
        if end_date < request.start_date:
            raise ValueError("推进日期不能早于模拟账户开始日期")
        running = replace(
            current,
            status="RUNNING",
            updated_at=datetime.now(UTC).isoformat(),
            error=None,
        )
        self._write(running)
        try:
            completed = self.backtests.run(replace(request, end_date=end_date))
            if not bool(completed.result.summary.get("metrics_reliable", False)):
                raise ValueError("模拟账户结果未通过当前可信度审计")
            updated = replace(
                running,
                status="ACTIVE",
                updated_at=datetime.now(UTC).isoformat(),
                last_date=end_date.isoformat(),
                last_run_id=completed.result.run_id,
            )
            self._write(updated)
            return updated
        except Exception as exc:
            failed = replace(
                running,
                status="FAILED",
                updated_at=datetime.now(UTC).isoformat(),
                error=f"{type(exc).__name__}: {exc}"[:2000],
            )
            self._write(failed)
            raise

    def latest_run_dir(self, account: PaperAccountRecord) -> Path | None:
        """Return the current account snapshot's normal backtest directory."""

        if not account.last_run_id:
            return None
        path = self.backtests.runs_root / account.last_run_id
        return path if path.exists() else None

    def go_live_checklist(self, account_id: str) -> GoLiveChecklist:
        """Evaluate the pre-flight checklist before advancing the account."""

        from quant_platform.application.paper_checklist import evaluate_go_live_checklist

        return evaluate_go_live_checklist(self, account_id)

    def _read(self, account_id: str) -> PaperAccountRecord:
        path = self.root / account_id / "account.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        return PaperAccountRecord(
            account_id=str(raw["account_id"]),
            display_name=str(raw["display_name"]),
            status=str(raw["status"]),
            created_at=str(raw["created_at"]),
            updated_at=str(raw["updated_at"]),
            last_date=(str(raw["last_date"]) if raw.get("last_date") else None),
            last_run_id=(str(raw["last_run_id"]) if raw.get("last_run_id") else None),
            error=(str(raw["error"]) if raw.get("error") else None),
            request=dict(raw["request"]),
        )

    def _write(self, record: PaperAccountRecord) -> None:
        directory = self.root / record.account_id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "account.json"
        temporary = directory / "account.json.tmp"
        temporary.write_text(
            json.dumps(asdict(record), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        temporary.replace(target)

    @staticmethod
    def _serialize_request(request: BacktestRequest) -> dict[str, Any]:
        return {
            "strategy_plugin": request.strategy_plugin,
            "strategy_id": request.strategy_id,
            "strategy_parameters": request.strategy_parameters,
            "start_date": request.start_date.isoformat(),
            "end_date": request.end_date.isoformat(),
            "initial_cash": request.initial_cash,
            "top_n": request.top_n,
            "rebalance": request.rebalance,
            "risk_limits": request.risk_limits.to_dict(),
        }

    @staticmethod
    def _deserialize_request(value: dict[str, Any]) -> BacktestRequest:
        return BacktestRequest(
            strategy_plugin=str(value["strategy_plugin"]),
            strategy_id=str(value["strategy_id"]),
            strategy_parameters=dict(value["strategy_parameters"]),
            start_date=date.fromisoformat(str(value["start_date"])),
            end_date=date.fromisoformat(str(value["end_date"])),
            initial_cash=float(value["initial_cash"]),
            top_n=int(value["top_n"]),
            rebalance=str(value["rebalance"]),
            risk_limits=RiskLimits.from_mapping(
                value.get("risk_limits") if isinstance(value, dict) else None
            ),
        )
