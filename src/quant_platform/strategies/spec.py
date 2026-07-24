"""Declarative strategy metadata and parameter validation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from quant_platform.core.exceptions import ConfigurationError


class ParameterKind(StrEnum):
    """Input types supported by both YAML and the web parameter form."""

    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    STRING = "string"


@dataclass(frozen=True)
class StrategyParameter:
    """One validated, UI-renderable strategy parameter."""

    name: str
    label: str
    kind: ParameterKind
    default: int | float | bool | str
    description: str = ""
    minimum: int | float | None = None
    maximum: int | float | None = None
    choices: tuple[str, ...] = ()

    def parse(self, value: Any) -> int | float | bool | str:
        """Coerce and validate one configured value."""

        try:
            if self.kind == ParameterKind.INTEGER:
                if isinstance(value, bool):
                    raise ValueError
                parsed: int | float | bool | str = int(value)
            elif self.kind == ParameterKind.NUMBER:
                if isinstance(value, bool):
                    raise ValueError
                parsed = float(value)
            elif self.kind == ParameterKind.BOOLEAN:
                if isinstance(value, bool):
                    parsed = value
                elif str(value).strip().lower() in {"true", "1", "yes", "on"}:
                    parsed = True
                elif str(value).strip().lower() in {"false", "0", "no", "off"}:
                    parsed = False
                else:
                    raise ValueError
            else:
                parsed = str(value)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"Invalid value for strategy parameter {self.name}: {value!r}"
            ) from exc

        if isinstance(parsed, (int, float)) and not isinstance(parsed, bool):
            if self.minimum is not None and parsed < self.minimum:
                raise ConfigurationError(
                    f"Strategy parameter {self.name} must be >= {self.minimum}"
                )
            if self.maximum is not None and parsed > self.maximum:
                raise ConfigurationError(
                    f"Strategy parameter {self.name} must be <= {self.maximum}"
                )
        if self.choices and str(parsed) not in self.choices:
            raise ConfigurationError(
                f"Strategy parameter {self.name} must be one of {self.choices}"
            )
        return parsed


@dataclass(frozen=True)
class StrategyMetadata:
    """Stable description exposed to CLI, web, and experiment snapshots."""

    plugin_name: str
    display_name: str
    description: str
    parameters: tuple[StrategyParameter, ...]
    required_fields: frozenset[str]

    def defaults(self) -> dict[str, int | float | bool | str]:
        """Return a fresh default parameter mapping."""

        return {parameter.name: parameter.default for parameter in self.parameters}

    def validate_parameters(
        self, values: dict[str, Any]
    ) -> dict[str, int | float | bool | str]:
        """Validate known values and reject misspelled parameter names."""

        definitions = {parameter.name: parameter for parameter in self.parameters}
        unknown = sorted(set(values).difference(definitions))
        if unknown:
            raise ConfigurationError(
                f"Unknown parameters for strategy {self.plugin_name}: {unknown}"
            )
        return {
            name: definition.parse(values.get(name, definition.default))
            for name, definition in definitions.items()
        }
