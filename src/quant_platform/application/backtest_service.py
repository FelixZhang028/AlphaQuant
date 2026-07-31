"""Unified use case for configuring, running, and saving backtests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from quant_platform.backtest.engine import BacktestEngine
from quant_platform.backtest.result import BacktestResult
from quant_platform.backtest.run_store import BacktestRunStore
from quant_platform.core.config import load_yaml, require_mapping
from quant_platform.data.repositories.parquet_repository import (
    ParquetMarketDataRepository,
)
from quant_platform.execution.next_open import ExecutionConfig, NextOpenExecutionModel
from quant_platform.execution.order_generator import OrderGenerator
from quant_platform.plugins import default_registry
from quant_platform.risk.config import RiskLimits
from quant_platform.strategies.discovery import StrategyCatalog
from quant_platform.strategies.spec import StrategyMetadata
from quant_platform.universe.a_share import AShareUniverse, AShareUniverseConfig


def parse_date(value: date | str) -> date:
    """Parse common compact or ISO date values."""

    if isinstance(value, date):
        return value
    return datetime.strptime(str(value).replace("-", ""), "%Y%m%d").date()


@dataclass(frozen=True)
class BacktestRequest:
    """All user-selectable inputs for one backtest."""

    strategy_plugin: str
    strategy_id: str
    strategy_parameters: dict[str, Any]
    start_date: date
    end_date: date
    initial_cash: float
    top_n: int
    rebalance: str
    risk_limits: RiskLimits = field(default_factory=RiskLimits)


@dataclass(frozen=True)
class BacktestRun:
    """Completed in-memory result and its persisted artifact directory."""

    result: BacktestResult
    output_dir: Path
    config_snapshot: dict[str, Any]


class BacktestService:
    """Provide the same backtest workflow to every user interface."""

    def __init__(
        self,
        app_config_path: str | Path = "configs/app.yaml",
        strategy_catalog: StrategyCatalog | None = None,
    ) -> None:
        self.app_config_path = Path(app_config_path)
        self.catalog = strategy_catalog or StrategyCatalog()
        self.configs = self._load_component_configs()

    @property
    def runs_root(self) -> Path:
        """Return the configured artifact root."""

        runtime_dir = require_mapping(self.configs["app"], "app").get("runtime_dir", "runtime")
        return Path(str(runtime_dir)) / "runs"

    @property
    def run_store(self) -> BacktestRunStore:
        """Return lifecycle-aware access to persisted runs."""

        return BacktestRunStore(self.runs_root)

    def available_strategies(self) -> tuple[StrategyMetadata, ...]:
        """List automatically discovered strategies."""

        return self.catalog.metadata()

    def default_request(self) -> BacktestRequest:
        """Build UI/CLI defaults from the configured strategy and application."""

        strategy_section = require_mapping(self.configs["strategy"], "strategy")
        app = self.configs["app"]
        backtest = require_mapping(app, "backtest")
        portfolio = require_mapping(app, "portfolio")
        plugin = str(strategy_section["plugin"])
        metadata = self.catalog.get_metadata(plugin)
        configured_parameters = require_mapping(strategy_section, "parameters")
        parameters = metadata.validate_parameters(configured_parameters)
        risk_section = self.configs.get("risk", {}).get("risk", {})
        return BacktestRequest(
            strategy_plugin=plugin,
            strategy_id=str(strategy_section.get("id", plugin)),
            strategy_parameters=parameters,
            start_date=parse_date(str(backtest["start_date"])),
            end_date=parse_date(str(backtest["end_date"])),
            initial_cash=float(backtest["initial_cash"]),
            top_n=int(portfolio.get("top_n", 5)),
            rebalance=str(strategy_section.get("rebalance", "weekly")),
            risk_limits=RiskLimits.from_mapping(
                risk_section if isinstance(risk_section, dict) else {}
            ),
        )

    def build_engine(
        self, request: BacktestRequest | None = None
    ) -> tuple[BacktestEngine, dict[str, Any]]:
        """Validate a request and compose the configured backtest engine."""

        effective = request or self.default_request()
        self._validate_request(effective)
        app = self.configs["app"]
        universe_section = require_mapping(self.configs["universe"], "universe")
        filters = require_mapping(universe_section, "filters")
        universe = AShareUniverse(
            AShareUniverseConfig(
                symbols=tuple(str(symbol) for symbol in universe_section["symbols"]),
                exclude_st=bool(filters.get("exclude_st", True)),
                exclude_suspended=bool(filters.get("exclude_suspended", True)),
                minimum_listing_days=int(filters.get("minimum_listing_days", 0)),
                minimum_history_days=int(filters.get("minimum_history_days", 61)),
                minimum_average_amount=float(filters.get("minimum_average_amount", 0)),
            )
        )
        strategy = self.catalog.create(
            effective.strategy_plugin,
            effective.strategy_id,
            effective.strategy_parameters,
        )
        execution_section = require_mapping(self.configs["execution"], "execution")
        execution_config = ExecutionConfig(
            lot_size=int(execution_section.get("lot_size", 100)),
            commission_rate=float(execution_section.get("commission_rate", 0.0003)),
            minimum_commission=float(execution_section.get("minimum_commission", 5.0)),
            stamp_tax_rate=float(execution_section.get("stamp_tax_rate", 0.0005)),
            slippage_rate=float(execution_section.get("slippage_rate", 0.0005)),
            reject_unknown_status=execution_section.get("unknown_status_policy", "reject_trade")
            == "reject_trade",
        )
        repository_path = require_mapping(app, "data")["repository"]
        portfolio_section = require_mapping(app, "portfolio")
        registry = default_registry()
        engine = BacktestEngine(
            repository=ParquetMarketDataRepository(repository_path),
            universe=universe,
            strategy=strategy,
            portfolio=registry.create(
                "portfolio",
                str(portfolio_section.get("plugin", "equal_weight")),
                top_n=effective.top_n,
            ),
            order_generator=OrderGenerator(execution_config.lot_size),
            execution_model=NextOpenExecutionModel(execution_config),
            rebalance=effective.rebalance,
            risk_limits=effective.risk_limits,
        )
        return engine, self._config_snapshot(effective)

    def run(self, request: BacktestRequest | None = None) -> BacktestRun:
        """Run and persist one lifecycle-tracked backtest."""

        effective = request or self.default_request()
        snapshot = self._config_snapshot(effective)
        run_id = str(uuid4())
        store = self.run_store
        store.start(run_id, snapshot)
        try:
            store.mark_running(run_id)
            engine, _ = self.build_engine(effective)
            result = engine.run(
                effective.start_date,
                effective.end_date,
                effective.initial_cash,
                run_id=run_id,
            )
            output = result.save(self.runs_root, snapshot)
            store.complete(run_id)
            return BacktestRun(result=result, output_dir=output, config_snapshot=snapshot)
        except Exception as exc:
            store.fail(run_id, exc)
            raise

    def _load_component_configs(self) -> dict[str, Any]:
        app = load_yaml(self.app_config_path)
        universe = load_yaml(require_mapping(app, "universe")["config"])
        strategy = load_yaml(require_mapping(app, "strategy")["config"])
        execution = load_yaml(require_mapping(app, "execution")["config"])
        risk_reference = app.get("risk", {})
        if isinstance(risk_reference, dict) and risk_reference.get("config"):
            risk = load_yaml(risk_reference["config"])
        elif isinstance(risk_reference, dict):
            risk = {"risk": risk_reference}
        else:
            risk = {"risk": {}}
        return {
            "app": app,
            "universe": universe,
            "strategy": strategy,
            "execution": execution,
            "risk": risk,
        }

    @staticmethod
    def _validate_request(request: BacktestRequest) -> None:
        if request.end_date < request.start_date:
            raise ValueError("end_date must not be before start_date")
        if request.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if request.top_n <= 0:
            raise ValueError("top_n must be positive")
        if request.rebalance not in {"daily", "weekly", "monthly"}:
            raise ValueError(f"Unsupported rebalance frequency: {request.rebalance}")
        request.risk_limits.validate()

    def _config_snapshot(self, request: BacktestRequest) -> dict[str, Any]:
        snapshot = deepcopy(self.configs)
        strategy = require_mapping(snapshot["strategy"], "strategy")
        strategy.update(
            {
                "id": request.strategy_id,
                "plugin": request.strategy_plugin,
                "rebalance": request.rebalance,
                "parameters": deepcopy(request.strategy_parameters),
            }
        )
        backtest = require_mapping(snapshot["app"], "backtest")
        backtest.update(
            {
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
                "initial_cash": request.initial_cash,
            }
        )
        require_mapping(snapshot["app"], "portfolio")["top_n"] = request.top_n
        snapshot["risk"] = {"risk": request.risk_limits.to_dict()}
        return snapshot
