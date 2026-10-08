"""Typed inputs for the remaining local workspace tools."""

from datetime import date
from typing import Any, Literal

from pydantic import Field

from quant_platform.api.schemas import BacktestInput, InputModel


class ModelSettingsInput(InputModel):
    base_url: str = Field("", max_length=2000)
    model: str = Field("", max_length=200)
    api_key: str | None = Field(None, max_length=4000)
    set_default: bool = False


class CredentialInput(InputModel):
    token: str | None = Field(None, max_length=4000)
    username: str | None = Field(None, max_length=200)
    password: str | None = Field(None, max_length=4000)
    base_url: str | None = Field(None, max_length=2000)


class ProxyInput(InputModel):
    enabled: bool
    address: str = Field(max_length=2000)


class PythonInput(InputModel):
    code: str = Field(min_length=1, max_length=300000)
    display_name: str = Field("", max_length=200)
    description: str = Field("", max_length=4000)
    risk_acknowledged: bool = False
    source: Literal["editor", "upload"] = "editor"


class CustomFactorInput(InputModel):
    name: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$", max_length=80)
    display_name: str = Field("", max_length=200)
    description: str = Field("", max_length=2000)
    field: str
    operator: str
    window: int = Field(ge=1, le=500, strict=True)
    window2: int | None = Field(None, ge=1, le=500, strict=True)
    direction: Literal[-1, 1] | None = None


class CombinationInput(InputModel):
    factor_names: list[str] = Field(min_length=2, max_length=20)
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    mode: Literal["equal", "manual", "ic"] = "equal"
    custom_weights: dict[str, float] | None = None
    clip: bool = True
    missing: Literal["drop", "median"] = "drop"
    horizon: Literal[1, 5, 10, 20] = 5
    n_groups: Literal[5, 10] = 5


class CombinationPrepareInput(InputModel):
    task_id: str
    base_request: BacktestInput | None = None


class NLInput(InputModel):
    description: str = Field(min_length=1, max_length=10000)
    provider: str | None = None


class ChatInput(InputModel):
    analysis_task_id: str
    message: str = Field(min_length=1, max_length=10000)
    previous_task_id: str | None = None


class XTickInput(InputModel):
    category_id: int
    api_id: int
    parameters: dict[str, str | int | float] = Field(default_factory=dict)


class BackfillInput(InputModel):
    start_date: date
    end_date: date
    datasets: list[Literal["bars", "actions", "derived"]] = Field(min_length=1)


class ExternalInput(InputModel):
    content: str = Field(min_length=1, max_length=5000000)
    mapping: dict[str, str] | None = None
    unit: Literal["股", "手"] = "股"
    raw_prices: bool = True
    duplicate_confirmed: bool = False


class PlanInput(InputModel):
    title: str = Field(min_length=1, max_length=200)
    request: BacktestInput | None = None
    run_id: str | None = None
    plan_id: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)


class PlanRef(InputModel):
    plan_id: str
    revision: int = Field(ge=1, strict=True)


class PlanCompareInput(InputModel):
    versions: list[PlanRef] = Field(min_length=2, max_length=4)


class PlanRestoreInput(InputModel):
    request: BacktestInput | None = None
