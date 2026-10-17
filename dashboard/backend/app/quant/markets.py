"""The stock pools a backtest can run on: the user's own pool, or an index as it was on each day."""

from __future__ import annotations

from typing import Any

from quant_platform.application.backtest_service import BacktestService
from quant_platform.data.index_constituents import CHECKS_TABLE, INDEX_UNIVERSES, checked_range, index_name

from .runtime import market_repository

CURRENT_POOL = "当前股票池"


def market_options() -> list[dict[str, Any]]:
    """The user's pool first, then each index with the dates its member history covers."""

    checks = market_repository().read_table(CHECKS_TABLE)
    options: list[dict[str, Any]] = [{"value": CURRENT_POOL, "label": "当前股票池", "available": True}]
    for index_symbol in INDEX_UNIVERSES:
        covered = checked_range(checks, index_symbol)
        options.append({
            "value": index_symbol,
            "label": f"{index_name(index_symbol)}历史成分股",
            "available": covered is not None,
            "start_date": covered[0].isoformat() if covered else None,
            "end_date": covered[1].isoformat() if covered else None,
        })
    return options


def use_market(service: BacktestService, market: str) -> None:
    """Point the service at the chosen pool. An index is used as it was on each day, never today's list."""

    if market == CURRENT_POOL:
        return
    if market not in INDEX_UNIVERSES:
        raise ValueError("不支持这个股票范围，请选择当前股票池或列表里的指数。")
    section = service.configs["universe"].setdefault("universe", {})
    section["mode"] = "historical"
    section["index"] = market
