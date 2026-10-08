"""Discriminated task submissions and query responses."""

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from quant_platform.api.schemas import (
    FactorEvaluationInput,
    InputModel,
    OptimizationInput,
    RunInput,
    UpdateInput,
    WalkForwardInput,
)
from quant_platform.api.workspace_schemas import ChatInput, CombinationInput, NLInput, XTickInput

TaskStatus = Literal[
    "QUEUED",
    "RUNNING",
    "CANCEL_REQUESTED",
    "SUCCESS",
    "PARTIAL",
    "FAILED",
    "CANCELLED",
    "INTERRUPTED",
]
TaskKind = Literal[
    "backtest",
    "optimization",
    "walk_forward",
    "factor_evaluation",
    "data_update",
    "ai_analysis",
    "nl_strategy",
    "factor_combination",
    "xtick_query",
    "ai_chat",
]


class BacktestTask(InputModel):
    kind: Literal["backtest"]
    input: RunInput


class OptimizationTask(InputModel):
    kind: Literal["optimization"]
    input: OptimizationInput


class WalkForwardTask(InputModel):
    kind: Literal["walk_forward"]
    input: WalkForwardInput


class FactorTask(InputModel):
    kind: Literal["factor_evaluation"]
    input: FactorEvaluationInput


class DataTask(InputModel):
    kind: Literal["data_update"]
    input: UpdateInput


class AIInput(InputModel):
    symbol: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9.^=-]+$")
    trade_date: date
    lookback_days: int = Field(120, ge=20, le=250, strict=True)
    debate_rounds: int = Field(1, ge=0, le=4, strict=True)
    use_cache: bool = True
    provider: str | None = None
    stock_source: Literal["local", "akshare", "tonghuashun", "eastmoney", "yfinance"] = "local"
    news_sources: list[Literal["eastmoney", "cls", "global_em"]] = Field(default_factory=list)


class AITask(InputModel):
    kind: Literal["ai_analysis"]
    input: AIInput


class NLTask(InputModel):
    kind: Literal["nl_strategy"]
    input: NLInput


class CombinationTask(InputModel):
    kind: Literal["factor_combination"]
    input: CombinationInput


class XTickTask(InputModel):
    kind: Literal["xtick_query"]
    input: XTickInput


class ChatTask(InputModel):
    kind: Literal["ai_chat"]
    input: ChatInput


Submission = Annotated[
    BacktestTask
    | OptimizationTask
    | WalkForwardTask
    | FactorTask
    | DataTask
    | AITask
    | NLTask
    | CombinationTask
    | XTickTask
    | ChatTask,
    Field(discriminator="kind"),
]


class ProgressResponse(BaseModel):
    stage: str
    completed: int
    total: int | None


class TaskResponse(BaseModel):
    id: str
    kind: TaskKind
    status: TaskStatus
    retry_of: str | None
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None
    cancel_requested: bool
    progress: ProgressResponse
    error: dict[str, Any] | None
    result_available: bool


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int
    offset: int
    limit: int
