"""YAML configuration loading with environment-variable expansion."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, cast

import yaml

from quant_platform.core.exceptions import ConfigurationError

_ENV_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def _expand_environment(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _expand_environment(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_environment(item) for item in value]
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda match: os.getenv(match.group(1), ""), value)
    return value


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML mapping and expand ``${ENV_VAR}`` placeholders."""

    config_path = Path(path)
    if not config_path.exists():
        raise ConfigurationError(f"Configuration file does not exist: {config_path}")
    try:
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid YAML in {config_path}: {exc}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ConfigurationError(
            f"Top-level YAML value must be a mapping: {config_path}"
        )
    return cast(dict[str, Any], _expand_environment(loaded))


def require_mapping(config: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a required mapping from configuration."""

    value = config.get(key)
    if not isinstance(value, dict):
        raise ConfigurationError(f"Missing or invalid mapping: {key}")
    return value
