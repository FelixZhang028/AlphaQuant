"""Explicit transport contracts; calculation stays in application services."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quant_platform.risk.config import RiskLimits

Frequency = Literal["daily", "weekly", "monthly"]
Objective = Literal["sharpe", "annual_return", "calmar", "max_drawdown"]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class DateRange(InputModel):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def dates_ordered(self):
        if self.end_date < self.start_date:
            raise ValueError("开始日期不能晚于结束日期")
        return self


class RiskInput(InputModel):
    enabled: bool = True
    max_total_weight: float = Field(1.0, ge=0, le=1)
    max_single_weight: float = Field(1.0, ge=0, le=1)
    max_positions: int = Field(10, gt=0, strict=True)
    minimum_cash_ratio: float = Field(0, ge=0, le=1)
    max_drawdown: float = Field(0.2, ge=0, le=1)
    daily_position_limits: bool = True
    drawdown_action: Literal["stop_new", "reduce", "liquidate"] = "stop_new"
    drawdown_target_weight: float = Field(0.5, ge=0, le=1)
    max_industry_weight: float = Field(1, ge=0, le=1)
    max_daily_loss: float = Field(1, ge=0, le=1)
    max_rebalance_turnover: float = Field(2, ge=0, le=2)

    @model_validator(mode="after")
    def business_limits(self):
        RiskLimits.from_mapping(self.model_dump())
        return self


class BacktestInput(DateRange):
    snapshot_run_id: str | None = None
    plan_id: str | None = None
    plan_revision: int | None = Field(None, ge=1, strict=True)
    strategy_plugin: str = Field(min_length=1, max_length=128)
    strategy_id: str = Field(min_length=1, max_length=256)
    strategy_parameters: dict[str, int | float | bool | str] = Field(default_factory=dict)
    initial_cash: float = Field(gt=0)
    top_n: int = Field(gt=0, strict=True)
    rebalance: Frequency
    portfolio_method: (
        Literal["equal_weight", "inverse_volatility", "risk_parity", "mean_variance"] | None
    ) = None
    universe_mode: Literal["fixed", "historical"] | None = None
    risk_limits: RiskInput | None = None


class RunInput(InputModel):
    request: BacktestInput
    confirmed: bool = Field(False, strict=True)
    plan_title: str | None = Field(None, max_length=256)
    plan_inputs: dict[str, Any] = Field(default_factory=dict)


class IdeaInput(DateRange):
    plan_id: str | None = None
    plan_revision: int | None = Field(None, ge=1, strict=True)
    idea: Literal["趋势上涨", "短期超跌", "低波动"]
    initial_cash: float = Field(gt=0)
    top_n: int = Field(ge=1, le=100, strict=True)
    rebalance: Frequency


class CompareInput(InputModel):
    run_ids: list[str] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def distinct(self):
        if len(set(self.run_ids)) != len(self.run_ids):
            raise ValueError("请选择不同的回测记录")
        return self


class GridInput(InputModel):
    baseline_run_id: str
    parameter_grid: dict[str, list[int | float | bool | str]]
    objective: Objective = "sharpe"
    max_drawdown_limit: float | None = Field(None, ge=0, le=1)
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def bounded_grid(self):
        count = 1
        if not self.parameter_grid:
            raise ValueError("参数网格不能为空")
        for values in self.parameter_grid.values():
            if not values:
                raise ValueError("每个参数至少需要一个候选值")
            count *= len(values)
        if count > 100:
            raise ValueError("单次实验最多100组")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期")
        return self


class OptimizationInput(GridInput):
    max_workers: Literal[1, 2, 4] = 1


class WalkForwardInput(GridInput):
    training_months: int = Field(12, ge=3, strict=True)
    test_months: int = Field(3, ge=1, strict=True)
    step_months: int = Field(3, ge=1, strict=True)
    max_windows: int = Field(12, ge=1, le=24, strict=True)


class PackageInput(InputModel):
    definition: dict[str, Any]
    top_n: int = Field(ge=1, le=50, strict=True)
    rebalance: Frequency
    revision_of: str | None = None


class CopyInput(InputModel):
    name: str | None = Field(None, max_length=256)


class PackageRequestInput(InputModel):
    package: dict[str, Any]
    base_request: BacktestInput | None = None


class UpdateInput(DateRange):
    datasets: list[
        Literal["security_master", "daily_bars", "corporate_actions", "benchmark_bars"]
    ] = Field(min_length=1)
    market_source_order: list[str] | None = None
    allow_market_fallback: bool | None = None
    benchmark_symbols: list[str] | None = None


class SymbolInput(InputModel):
    symbols: list[str] = Field(min_length=1)


class UniverseFilterInput(InputModel):
    exclude_st: bool
    exclude_suspended: bool
    minimum_listing_days: int = Field(ge=0, strict=True)
    minimum_history_days: int = Field(ge=1, strict=True)
    minimum_average_amount: float = Field(ge=0)


class KnowledgeInput(InputModel):
    content: str = Field(min_length=1, max_length=50000)
    source: str = Field("我的观点", max_length=1000)


class FactorEvaluationInput(DateRange):
    factor_name: str
    symbols: list[str] | None = None
    horizon: Literal[1, 5, 10, 20] = 5
    n_groups: Literal[5, 10] = 5
    neutralization: Literal["none", "industry", "size", "both"] = "none"
