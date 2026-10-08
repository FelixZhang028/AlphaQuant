"""Safe configuration service for the user-managed A-share universe."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from quant_platform.core.config import load_yaml, require_mapping
from quant_platform.core.exceptions import ConfigurationError
from quant_platform.data.repositories.parquet_repository import (
    ParquetMarketDataRepository,
)

_SEPARATOR_PATTERN = re.compile(r"[\s,，;；]+")
_SUFFIX_PATTERN = re.compile(r"^(\d{6})[.]?(SH|SZ|BJ)$")
_PREFIX_PATTERN = re.compile(r"^(SH|SZ|BJ)[.]?(\d{6})$")


@dataclass(frozen=True)
class UniverseSettings:
    """Editable A-share universe settings."""

    universe_id: str
    symbols: tuple[str, ...]
    exclude_st: bool
    exclude_suspended: bool
    minimum_listing_days: int
    minimum_history_days: int
    minimum_average_amount: float


def normalize_a_share_symbol(value: str) -> str:
    """Normalize a common six-digit or exchange-qualified A-share symbol."""

    compact = re.sub(r"[\s_-]+", "", str(value).strip().upper())
    suffix = _SUFFIX_PATTERN.fullmatch(compact)
    if suffix:
        return f"{suffix.group(1)}.{suffix.group(2)}"
    prefix = _PREFIX_PATTERN.fullmatch(compact)
    if prefix:
        return f"{prefix.group(2)}.{prefix.group(1)}"
    if not re.fullmatch(r"\d{6}", compact):
        raise ConfigurationError(f"无法识别股票代码：{value}")
    if compact.startswith("6"):
        exchange = "SH"
    elif compact.startswith(("0", "3")):
        exchange = "SZ"
    elif compact.startswith(("4", "8", "9")):
        exchange = "BJ"
    else:
        raise ConfigurationError(f"无法根据代码判断交易所：{value}")
    return f"{compact}.{exchange}"


def parse_symbol_text(raw: str) -> tuple[str, ...]:
    """Parse newline- or comma-separated symbols, preserving first-seen order."""

    values = [item for item in _SEPARATOR_PATTERN.split(raw.strip()) if item]
    normalized: list[str] = []
    for value in values:
        symbol = normalize_a_share_symbol(value)
        if symbol not in normalized:
            normalized.append(symbol)
    return tuple(normalized)


class UniverseManagementService:
    """Load and atomically update the configured stock universe."""

    def __init__(self, app_config_path: str | Path = "configs/app.yaml") -> None:
        self.app_config_path = Path(app_config_path)
        self.app = load_yaml(self.app_config_path)
        self.universe_path = Path(str(require_mapping(self.app, "universe")["config"]))
        repository_path = require_mapping(self.app, "data")["repository"]
        self.repository = ParquetMarketDataRepository(repository_path)

    def load(self) -> UniverseSettings:
        """Return validated editable settings from the current universe YAML."""

        raw = load_yaml(self.universe_path)
        universe = require_mapping(raw, "universe")
        filters = require_mapping(universe, "filters")
        symbols = tuple(
            dict.fromkeys(
                normalize_a_share_symbol(str(item)) for item in universe.get("symbols", [])
            )
        )
        return UniverseSettings(
            universe_id=str(universe.get("id", "a_share_personal")),
            symbols=symbols,
            exclude_st=bool(filters.get("exclude_st", True)),
            exclude_suspended=bool(filters.get("exclude_suspended", True)),
            minimum_listing_days=int(filters.get("minimum_listing_days", 120)),
            minimum_history_days=int(filters.get("minimum_history_days", 61)),
            minimum_average_amount=float(filters.get("minimum_average_amount", 20_000_000)),
        )

    def add_symbols(self, raw_symbols: str | tuple[str, ...]) -> UniverseSettings:
        """Append normalized symbols and persist the updated universe."""

        additions = (
            parse_symbol_text(raw_symbols)
            if isinstance(raw_symbols, str)
            else tuple(normalize_a_share_symbol(value) for value in raw_symbols)
        )
        current = self.load()
        updated = replace(current, symbols=tuple(dict.fromkeys((*current.symbols, *additions))))
        self.save(updated)
        return updated

    def remove_symbols(self, symbols: list[str] | tuple[str, ...]) -> UniverseSettings:
        """Remove selected symbols while keeping at least one configured stock."""

        removing = {normalize_a_share_symbol(value) for value in symbols}
        current = self.load()
        remaining = tuple(symbol for symbol in current.symbols if symbol not in removing)
        if not remaining:
            raise ConfigurationError("股票池至少需要保留一只股票")
        updated = replace(current, symbols=remaining)
        self.save(updated)
        return updated

    def save(self, settings: UniverseSettings) -> None:
        """Atomically persist symbols and filters without dropping custom keys."""

        if not settings.symbols:
            raise ConfigurationError("股票池至少需要一只股票")
        if settings.minimum_listing_days < 0 or settings.minimum_history_days < 1:
            raise ConfigurationError("上市天数不能为负，最少历史天数必须大于零")
        if settings.minimum_average_amount < 0:
            raise ConfigurationError("最低平均成交额不能为负数")

        raw = load_yaml(self.universe_path)
        universe = require_mapping(raw, "universe")
        filters = universe.get("filters")
        if not isinstance(filters, dict):
            filters = {}
            universe["filters"] = filters
        universe.update(
            {
                "id": settings.universe_id.strip() or "a_share_personal",
                "symbols": list(dict.fromkeys(settings.symbols)),
            }
        )
        filters.update(
            {
                "exclude_st": settings.exclude_st,
                "exclude_suspended": settings.exclude_suspended,
                "minimum_listing_days": settings.minimum_listing_days,
                "minimum_history_days": settings.minimum_history_days,
                "minimum_average_amount": settings.minimum_average_amount,
            }
        )
        self.universe_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.universe_path.with_suffix(self.universe_path.suffix + ".tmp")
        temporary.write_text(
            yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        temporary.replace(self.universe_path)

    def describe_symbols(self, symbols: tuple[str, ...] | None = None) -> pd.DataFrame:
        """Return names and local-data coverage for configured symbols."""

        selected = symbols or self.load().symbols
        base = pd.DataFrame({"symbol": list(selected)})
        master = self.repository.read_table("security_master")
        if not master.empty and "symbol" in master.columns:
            columns = [column for column in ("symbol", "name", "exchange") if column in master]
            base = base.merge(master[columns].drop_duplicates("symbol"), on="symbol", how="left")
        bars = self.repository.read_table("daily_bars")
        if bars.empty or not {"symbol", "trade_date"}.issubset(bars.columns):
            base["local_rows"] = 0
            base["local_start_date"] = pd.NaT
            base["local_end_date"] = pd.NaT
        else:
            working = bars[bars["symbol"].isin(selected)].copy()
            working["trade_date"] = pd.to_datetime(working["trade_date"])
            coverage = (
                working.groupby("symbol", observed=True)["trade_date"]
                .agg(local_rows="nunique", local_start_date="min", local_end_date="max")
                .reset_index()
            )
            base = base.merge(coverage, on="symbol", how="left")
            base["local_rows"] = base["local_rows"].fillna(0).astype(int)
        if "name" not in base:
            base["name"] = pd.NA
        if "exchange" not in base:
            base["exchange"] = base["symbol"].str.rsplit(".", n=1).str[-1]
        return base[
            [
                "symbol",
                "name",
                "exchange",
                "local_rows",
                "local_start_date",
                "local_end_date",
            ]
        ]

    def search_security_master(self, query: str, *, limit: int = 50) -> pd.DataFrame:
        """Search the local security master by stock code or Chinese name."""

        master = self.repository.read_table("security_master")
        required = {"symbol", "name"}
        if not query.strip() or master.empty or not required.issubset(master.columns):
            return pd.DataFrame(columns=["symbol", "name", "exchange"])
        text = query.strip()
        mask = master["symbol"].astype(str).str.contains(text, case=False, regex=False)
        mask |= master["name"].astype(str).str.contains(text, case=False, regex=False)
        columns = [column for column in ("symbol", "name", "exchange") if column in master]
        return (
            master.loc[mask, columns].drop_duplicates("symbol").head(limit).reset_index(drop=True)
        )


def update_universe_settings(settings: UniverseSettings, **changes: Any) -> UniverseSettings:
    """Typed convenience wrapper used by the Streamlit form."""

    return replace(settings, **changes)
