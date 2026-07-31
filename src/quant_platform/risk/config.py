"""Configurable portfolio risk limits shared by backtests and paper runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class RiskLimits:
    """Small, explainable set of portfolio-level pre-trade limits."""

    enabled: bool = True
    max_total_weight: float = 1.0
    max_single_weight: float = 1.0
    max_positions: int = 10
    minimum_cash_ratio: float = 0.0
    max_drawdown: float = 0.20

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> RiskLimits:
        """Build and validate limits from a YAML-compatible mapping."""

        raw = value or {}
        limits = cls(
            enabled=bool(raw.get("enabled", True)),
            max_total_weight=float(raw.get("max_total_weight", 1.0)),
            max_single_weight=float(raw.get("max_single_weight", 1.0)),
            max_positions=int(raw.get("max_positions", 10)),
            minimum_cash_ratio=float(raw.get("minimum_cash_ratio", 0.0)),
            max_drawdown=float(raw.get("max_drawdown", 0.20)),
        )
        limits.validate()
        return limits

    def validate(self) -> None:
        """Reject limits that would make risk decisions ambiguous."""

        for name, value in (
            ("max_total_weight", self.max_total_weight),
            ("max_single_weight", self.max_single_weight),
            ("minimum_cash_ratio", self.minimum_cash_ratio),
            ("max_drawdown", self.max_drawdown),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.max_positions <= 0:
            raise ValueError("max_positions must be positive")
        if self.max_total_weight > 1.0 - self.minimum_cash_ratio + 1e-9:
            raise ValueError("max_total_weight must leave at least minimum_cash_ratio in cash")

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable representation."""

        return asdict(self)


def load_risk_limits(path: str | Path) -> RiskLimits:
    """Load limits from a standalone risk YAML file."""

    config_path = Path(path)
    if not config_path.exists():
        return RiskLimits()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("risk config must be a mapping")
    section = raw.get("risk", raw)
    if not isinstance(section, dict):
        raise ValueError("risk section must be a mapping")
    return RiskLimits.from_mapping(section)


def save_risk_limits(path: str | Path, limits: RiskLimits) -> None:
    """Persist validated limits for later backtests and paper runs."""

    limits.validate()
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump({"risk": limits.to_dict()}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
