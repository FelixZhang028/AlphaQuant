"""可信度审计评级逻辑的单元测试。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from quant_platform.backtest.credibility import audit_credibility, audit_persisted_run
from quant_platform.backtest.validity import CURRENT_AUDIT_VERSION

_EXECUTION = {
    "historical_fees": True,
    "max_participation": 0.01,
    "impact_coefficient": 0.001,
    "slippage_rate": 0.0005,
    "unknown_status_policy": "reject_trade",
}

_SUMMARY = {
    "initial_cash": 1_000_000.0,
    "commission": 1_200.0,
    "stamp_tax": 800.0,
    "transfer_fee": 20.0,
    "slippage_cost": 1_500.0,
    "total_transaction_cost": 3_520.0,
    "transaction_cost_to_initial_cash": 0.00352,
    "delisting_settlements": 0,
}


def _validity(
    *,
    issues: list[tuple[str, str, str]] | None = None,
    status: str = "VALID",
    metrics_reliable: bool = True,
    unknown_status_orders: int = 0,
    missing_adj_factor_rows: int = 0,
    observations: int = 244,
    gap: int = 8,
    legacy: bool = False,
) -> dict[str, Any]:
    return {
        "status": status,
        "metrics_reliable": metrics_reliable,
        "issues": [
            {"code": code, "severity": severity, "message": message}
            for code, severity, message in (issues or [])
        ],
        "observations": observations,
        "maximum_calendar_gap_days": gap,
        "unknown_status_orders": unknown_status_orders,
        "missing_adj_factor_rows": missing_adj_factor_rows,
        "audit_version": CURRENT_AUDIT_VERSION,
        "legacy_unverified": legacy,
    }


def _audit(
    *,
    validity: dict[str, Any] | None = None,
    summary: dict[str, Any] | None = None,
    execution: dict[str, Any] | None = None,
    orders: pd.DataFrame | None = None,
    fills: pd.DataFrame | None = None,
    run_kind: str = "single",
):
    return audit_credibility(
        validity if validity is not None else _validity(),
        summary if summary is not None else dict(_SUMMARY),
        _EXECUTION if execution is None else execution,
        orders if orders is not None else pd.DataFrame(),
        fills if fills is not None else pd.DataFrame(),
        run_kind=run_kind,
    )


def _dimension(report, key: str):
    return next(dimension for dimension in report.dimensions if dimension.key == key)


def test_clean_run_grades_a() -> None:
    report = _audit()

    assert report.grade == "A"
    assert report.metrics_reliable
    assert all(dimension.status == "pass" for dimension in report.dimensions)
    assert "通过全部审计检查" in report.headline
    assert report.transaction_cost_ratio == 0.00352


def test_fixed_universe_single_warning_grades_b() -> None:
    report = _audit(
        validity=_validity(
            issues=[("FIXED_UNIVERSE", "WARNING", "固定股票池警告。")],
            status="WARNING",
        )
    )

    assert report.grade == "B"
    assert _dimension(report, "sample_bias").status == "warn"


def test_typical_in_sample_run_grades_c() -> None:
    report = _audit(
        validity=_validity(
            issues=[
                ("FIXED_UNIVERSE", "WARNING", "固定股票池警告。"),
                ("IN_SAMPLE_ONLY", "WARNING", "样本内回测警告。"),
            ],
            status="WARNING",
        )
    )

    assert report.grade == "C"
    sample_bias = _dimension(report, "sample_bias")
    assert sample_bias.status == "warn"
    assert len([f for f in sample_bias.findings if f.severity == "warn"]) == 2


def test_error_issue_grades_d() -> None:
    report = _audit(
        validity=_validity(
            issues=[("EXCESSIVE_DATE_GAP", "ERROR", "净值日期断档 40 天。")],
            status="INVALID",
            metrics_reliable=False,
        )
    )

    assert report.grade == "D"
    assert not report.metrics_reliable
    assert _dimension(report, "data_integrity").status == "fail"


def test_legacy_run_grades_d() -> None:
    report = _audit(validity=_validity(legacy=True, status="INVALID", metrics_reliable=False))

    assert report.grade == "D"
    assert _dimension(report, "data_integrity").status == "fail"


def test_unknown_status_orders_fail_lookahead() -> None:
    report = _audit(
        validity=_validity(
            issues=[("UNKNOWN_STATUS_ORDERS", "ERROR", "订单被拒绝。")],
            status="INVALID",
            metrics_reliable=False,
            unknown_status_orders=3,
        )
    )

    assert report.grade == "D"
    assert _dimension(report, "lookahead_guard").status == "fail"


def test_missing_adj_factor_warns_lookahead() -> None:
    report = _audit(
        validity=_validity(
            issues=[("MISSING_ADJ_FACTOR", "WARNING", "复权因子缺失。")],
            status="WARNING",
            missing_adj_factor_rows=5,
        )
    )

    assert report.grade == "B"
    assert _dimension(report, "lookahead_guard").status == "warn"


def test_permissive_unknown_policy_warns() -> None:
    report = _audit(
        validity=_validity(status="WARNING", metrics_reliable=True),
        execution={**_EXECUTION, "unknown_status_policy": "allow"},
    )

    assert report.grade == "B"
    assert _dimension(report, "lookahead_guard").status == "warn"


def test_fixed_fees_warn_cost_realism() -> None:
    report = _audit(execution={**_EXECUTION, "historical_fees": False})

    assert report.grade == "B"
    assert _dimension(report, "cost_realism").status == "warn"


def test_high_cost_ratio_warns_cost_realism() -> None:
    report = _audit(
        summary={
            **_SUMMARY,
            "total_transaction_cost": 180_000.0,
            "transaction_cost_to_initial_cash": 0.18,
        }
    )

    assert report.grade == "B"
    assert _dimension(report, "cost_realism").status == "warn"


def test_cost_breakdown_falls_back_to_fills() -> None:
    fills = pd.DataFrame(
        {
            "commission": [10.0, 20.0],
            "stamp_tax": [0.0, 5.0],
            "transfer_fee": [0.1, 0.2],
            "slippage_cost": [3.0, 4.0],
        }
    )
    report = _audit(
        summary={"initial_cash": 100_000.0},
        fills=fills,
    )

    assert report.grade == "A"
    assert report.total_transaction_cost == 42.3
    cost = _dimension(report, "cost_realism")
    assert cost.status == "pass"
    assert "费用分解" in cost.findings[0].message


def test_liquidity_rejections_warn_capacity() -> None:
    orders = pd.DataFrame(
        {
            "order_id": ["o1", "o2", "o3"],
            "reject_reason": ["LIQUIDITY_LIMIT", None, "OPEN_AT_UPPER_LIMIT"],
        }
    )
    report = _audit(orders=orders)

    assert report.grade == "B"
    capacity = _dimension(report, "capacity")
    assert capacity.status == "warn"
    assert "1 笔订单" in capacity.findings[0].message


def test_out_of_sample_run_noted_in_sample_bias() -> None:
    report = _audit(run_kind="walk_forward_oos")

    assert report.grade == "A"
    sample_bias = _dimension(report, "sample_bias")
    assert sample_bias.status == "pass"
    assert "样本外" in sample_bias.findings[0].message


def test_audit_persisted_run_reads_run_directory(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(json.dumps(_SUMMARY), encoding="utf-8")
    (run_dir / "validity_report.json").write_text(
        json.dumps(
            _validity(
                issues=[
                    ("FIXED_UNIVERSE", "WARNING", "固定股票池警告。"),
                    ("IN_SAMPLE_ONLY", "WARNING", "样本内回测警告。"),
                ],
                status="WARNING",
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "config.snapshot.yaml").write_text(
        yaml.safe_dump({"execution": {"execution": _EXECUTION}}), encoding="utf-8"
    )
    pd.DataFrame({"reject_reason": ["LIQUIDITY_LIMIT", None]}).to_parquet(
        run_dir / "orders.parquet", index=False
    )

    report = audit_persisted_run(run_dir)

    assert report.grade == "C"  # 样本偏差 + 容量约束两项警告
    assert report.observations == 244


def test_audit_persisted_run_tolerates_missing_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-legacy"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text("not-json", encoding="utf-8")

    report = audit_persisted_run(run_dir)

    # 无有效性报告 → 旧版未验证 → D；损坏文件不抛异常。
    assert report.grade == "D"
    assert not report.metrics_reliable
    assert report.validity_status == "INVALID"
