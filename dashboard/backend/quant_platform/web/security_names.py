"""Consistent security labels for UI tables, selectors and downloads."""

from functools import lru_cache
from pathlib import Path

import pandas as pd

from quant_platform.application.benchmarks import BENCHMARK_NAMES
from quant_platform.core.config import load_yaml
from quant_platform.core.exceptions import ConfigurationError

UNKNOWN_NAME = "未知名称"


def _text(value) -> str:
    return "" if pd.isna(value) else str(value).strip()


@lru_cache(maxsize=8)
def _read_names(path: str, modified: int, size: int) -> dict[str, str]:
    frame = pd.read_parquet(path)
    if not {"symbol", "name"}.issubset(frame.columns):
        return {}
    return {
        _text(symbol).upper(): _text(name)
        for symbol, name in zip(frame.symbol, frame.name, strict=True)
        if _text(symbol) and _text(name)
    }


def load_security_names(config_path: str = "configs/app.yaml") -> dict[str, str]:
    """Read local stock names, invalidating on master-file updates and cwd changes."""
    try:
        config = load_yaml(Path(config_path).resolve())
        path = (Path(config["data"]["repository"]) / "security_master.parquet").resolve()
        stat = path.stat()
        return dict(_read_names(str(path), stat.st_mtime_ns, stat.st_size))
    except (OSError, ValueError, KeyError, ConfigurationError):
        return {}


def security_label(symbol: str, names: dict[str, str]) -> str:
    name = _text(names.get(str(symbol).upper())) or UNKNOWN_NAME
    return f"{name}（{symbol}）"


def with_security_names(
    frame: pd.DataFrame,
    names: dict[str, str] | None = None,
    *,
    code_column: str | None = None,
    bare_codes: bool = False,
) -> pd.DataFrame:
    """Add names without changing codes, row order or the source frame.

    Bare numeric codes are resolved only when the caller supplies the asset
    namespace (e.g. stocks versus indices); ambiguous aliases remain unknown.
    """
    result = frame.copy()
    code_column = code_column or next(
        (column for column in ("symbol", "股票代码", "证券代码") if column in result), None
    )
    if code_column is None or code_column not in result:
        return result
    if names is None:
        names = {**load_security_names(), **BENCHMARK_NAMES}
    lookup = {str(code).upper(): name for code, name in names.items()}
    if bare_codes:
        aliases: dict[str, set[str]] = {}
        for code, name in lookup.items():
            aliases.setdefault(code.split(".")[0], set()).add(name)
        lookup.update(
            {code: next(iter(values)) for code, values in aliases.items() if len(values) == 1}
        )
    name_column = next(
        (column for column in ("股票名称", "证券名称", "name") if column in result),
        "股票名称" if code_column in ("股票代码", "证券代码") else "name",
    )
    codes = result[code_column].map(lambda value: _text(value).upper())
    if bare_codes:
        codes = codes.map(lambda value: value.zfill(6) if value.isdigit() else value)
    resolved = codes.map(lookup).fillna(UNKNOWN_NAME)
    if name_column in result:
        existing = result.pop(name_column).map(_text)
        resolved = existing.where(~existing.isin(["", UNKNOWN_NAME]), resolved)
    result.insert(result.columns.get_loc(code_column), name_column, resolved)
    return result


def xtick_security_names(frame: pd.DataFrame, request_type: str | None) -> pd.DataFrame:
    """Use the saved request's market type, never the current form's selection."""
    code_column = next((key for key in ("code", "symbol", "股票代码") if key in frame), None)
    if code_column is None:
        return frame.copy()
    names = (
        load_security_names()
        if request_type == "1"
        else (BENCHMARK_NAMES if request_type == "2" else {})
    )
    return with_security_names(frame, names, code_column=code_column, bare_codes=True)
