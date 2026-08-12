"""Use cases for P0 templates and P1 visual, zero-code strategies."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from quant_platform.application.backtest_service import (
    BacktestRequest,
    BacktestRun,
    BacktestService,
)
from quant_platform.core.exceptions import ConfigurationError
from quant_platform.strategies.rule_schema import RuleStrategyDefinition
from quant_platform.strategies.templates import StrategyPreset, get_beginner_template


@dataclass(frozen=True)
class StrategyPackage:
    """A rule definition plus the portfolio controls needed to reproduce it."""

    package_id: str
    name: str
    definition: RuleStrategyDefinition
    top_n: int
    rebalance: str
    source: str
    created_at: datetime

    def validate(self) -> None:
        self.definition.validate()
        if not 1 <= self.top_n <= 50:
            raise ConfigurationError("持股数量必须在1至50之间")
        if self.rebalance not in {"daily", "weekly", "monthly"}:
            raise ConfigurationError("调仓频率只能是每日、每周或每月")

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_version": 1,
            "package_id": self.package_id,
            "name": self.name,
            "definition": self.definition.to_dict(),
            "top_n": self.top_n,
            "rebalance": self.rebalance,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_mapping(cls, value: Any) -> StrategyPackage:
        if not isinstance(value, dict) or int(value.get("package_version", 0)) != 1:
            raise ConfigurationError("不支持的零代码策略文件")
        result = cls(
            package_id=str(value.get("package_id", "")),
            name=str(value.get("name", "")),
            definition=RuleStrategyDefinition.from_mapping(value.get("definition")),
            top_n=int(value.get("top_n", 0)),
            rebalance=str(value.get("rebalance", "")),
            source=str(value.get("source", "saved")),
            created_at=datetime.fromisoformat(str(value.get("created_at"))),
        )
        result.validate()
        return result


class StrategyPackageStore:
    """Persist safe visual strategies as portable JSON files."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def save(
        self,
        definition: RuleStrategyDefinition,
        *,
        top_n: int,
        rebalance: str,
        source: str = "visual_builder",
    ) -> StrategyPackage:
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", definition.strategy_id).strip("-")
        package = StrategyPackage(
            package_id=f"{safe or 'strategy'}-{uuid4().hex[:8]}",
            name=definition.name,
            definition=definition,
            top_n=top_n,
            rebalance=rebalance,
            source=source,
            created_at=datetime.now(UTC),
        )
        package.validate()
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{package.package_id}.json"
        path.write_text(
            json.dumps(package.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return package

    def load(self, package_id: str) -> StrategyPackage:
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", package_id):
            raise ConfigurationError("策略文件编号不合法")
        path = self.root / f"{package_id}.json"
        if not path.is_file():
            raise ConfigurationError(f"策略不存在：{package_id}")
        return StrategyPackage.from_mapping(json.loads(path.read_text(encoding="utf-8")))

    def list(self) -> tuple[StrategyPackage, ...]:
        if not self.root.exists():
            return ()
        packages: list[StrategyPackage] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                packages.append(
                    StrategyPackage.from_mapping(json.loads(path.read_text(encoding="utf-8")))
                )
            except (ConfigurationError, json.JSONDecodeError, ValueError):
                continue
        return tuple(sorted(packages, key=lambda item: item.created_at, reverse=True))

    def copy(self, package_id: str, *, name: str | None = None) -> StrategyPackage:
        original = self.load(package_id)
        definition = RuleStrategyDefinition.from_mapping(
            {
                **original.definition.to_dict(),
                "strategy_id": f"{original.definition.strategy_id}_copy",
                "name": name or f"{original.name}（副本）",
            }
        )
        return self.save(
            definition,
            top_n=original.top_n,
            rebalance=original.rebalance,
            source=f"copy:{original.package_id}",
        )


class StrategyStudioService:
    """Compose templates or builder packages into normal, audited backtests."""

    def __init__(self, backtests: BacktestService) -> None:
        self.backtests = backtests
        self.store = StrategyPackageStore(backtests.runs_root.parent / "strategy_definitions")

    def template_package(self, template_id: str, style: str) -> StrategyPackage:
        template = get_beginner_template(template_id)
        try:
            preset: StrategyPreset = template.presets[style]
        except KeyError as exc:
            raise ConfigurationError(f"未知模板风格：{style}") from exc
        return StrategyPackage(
            package_id=f"template-{template_id}-{style}",
            name=preset.definition.name,
            definition=preset.definition,
            top_n=preset.top_n,
            rebalance=preset.rebalance,
            source=f"template:{template_id}:{style}",
            created_at=datetime.now(UTC),
        )

    def build_request(
        self,
        package: StrategyPackage,
        *,
        base_request: BacktestRequest | None = None,
    ) -> BacktestRequest:
        package.validate()
        base = base_request or self.backtests.default_request()
        return replace(
            base,
            strategy_plugin="rule_builder",
            strategy_id=package.definition.strategy_id,
            strategy_parameters={"definition_json": package.definition.to_json()},
            top_n=package.top_n,
            rebalance=package.rebalance,
        )

    def run(
        self,
        package: StrategyPackage,
        *,
        base_request: BacktestRequest | None = None,
    ) -> BacktestRun:
        return self.backtests.run(self.build_request(package, base_request=base_request))

    @staticmethod
    def preflight(
        package: StrategyPackage, *, available_days: int | None = None
    ) -> tuple[str, ...]:
        package.validate()
        warnings: list[str] = []
        if package.rebalance == "daily":
            warnings.append("每日调仓可能产生较高换手率和交易成本。")
        if package.top_n <= 3:
            warnings.append("持股数量较少，单只股票波动对组合影响较大。")
        required = package.definition.minimum_history_days
        if available_days is not None and available_days < required:
            warnings.append(f"策略至少需要{required}个交易日历史，当前区间可能不足。")
        if len(package.definition.entry_rules) >= 6:
            warnings.append("条件较多，可能长期选不出股票。")
        return tuple(warnings)
