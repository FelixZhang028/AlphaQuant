"""运行时服务工厂：以绝对路径构造 vendored quant_platform 的各服务。

关键约定：
- AlphaQuant 的 yaml 内路径均为相对 CWD 的相对路径，服务构造期间用
  ``_backend_cwd`` 上下文临时切到 backend 根目录，构造完成后把
  runtime/repository 等路径改写为绝对路径，运行期不再依赖 CWD。
- 回测服务的 universe 与用户策略按用户从 SQLite 注入，实现多用户隔离。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

from quant_platform.application.backtest_service import BacktestService
from quant_platform.application.data_service import DataCenterService
from quant_platform.data.repositories.parquet_repository import (
    ParquetMarketDataRepository,
)
from quant_platform.data.repositories.raw_repository import RawDataRepository
from quant_platform.factors.alpha101 import alpha101_factors
from quant_platform.factors.builtins import builtin_factors
from quant_platform.factors.custom import build_custom_factor
from quant_platform.factors.evaluation import FactorEvaluator
from quant_platform.factors.registry import FactorRegistry
from quant_platform.risk.config import RiskLimits
from quant_platform.strategies.discovery import StrategyCatalog
from quant_platform.user_strategies.loader import UserStrategyLoader

from ..database import get_conn
from .symbols import to_canonical

log = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = BACKEND_ROOT / "configs" / "app.yaml"
MARKET_ROOT = BACKEND_ROOT / "data" / "market"
RUNTIME_ROOT = BACKEND_ROOT / "data" / "runtime"

_CHDIR_LOCK = threading.Lock()
# 数据更新（下载行情）为长任务且不可并发，同一进程内串行执行。
DATA_UPDATE_LOCK = threading.Lock()


@contextmanager
def _backend_cwd():
    """临时切换 CWD 到 backend 根，用于解析 yaml 内的相对路径。"""

    with _CHDIR_LOCK:
        previous = Path.cwd()
        os.chdir(BACKEND_ROOT)
        try:
            yield
        finally:
            os.chdir(previous)


def _abs(path_value: Any) -> Path:
    path = Path(str(path_value))
    return path if path.is_absolute() else BACKEND_ROOT / path


# --------------------------------------------------------------------------- #
# 行情仓库与证券名称
# --------------------------------------------------------------------------- #


def market_repository() -> ParquetMarketDataRepository:
    return ParquetMarketDataRepository(MARKET_ROOT)


def security_names() -> dict[str, str]:
    """证券主表 symbol -> name 映射（主表为空时返回空 dict）。"""

    master = market_repository().read_table("security_master")
    if master.empty or "name" not in master.columns:
        return {}
    return {
        str(symbol): str(name)
        for symbol, name in zip(master["symbol"], master["name"], strict=False)
    }


def local_market_ready() -> bool:
    """本地行情与交易日历是否就绪（否则回测/因子评估应引导用户先下载数据）。"""

    repo = market_repository()
    calendar = repo.read_table("trade_calendar")
    bars = repo.read_table("daily_bars")
    return not calendar.empty and not bars.empty


def local_data_bounds() -> tuple[date, date] | None:
    """本地 daily_bars 的 (最早, 最晚) 交易日；无数据时返回 None。"""

    return market_repository().daily_bar_bounds()


# --------------------------------------------------------------------------- #
# 用户配置读取（SQLite）
# --------------------------------------------------------------------------- #


def _user_universe(user_id: int) -> tuple[list[str], dict[str, Any]]:
    """返回该用户股票池（canonical 符号）与过滤设置。"""

    with get_conn() as conn:
        row = conn.execute("SELECT * FROM universe WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return [], {}
    symbols = [to_canonical(s) for s in json.loads(row["symbols"])]
    filters = {
        "exclude_st": bool(row["exclude_st"]),
        "exclude_suspended": bool(row["exclude_suspended"]),
        "minimum_listing_days": row["minimum_listing_days"],
        "minimum_history_days": row["minimum_history_days"],
        "minimum_average_amount": row["minimum_average_amount"],
    }
    return symbols, filters


def user_universe_symbols(user_id: int) -> list[str]:
    symbols, _ = _user_universe(user_id)
    return symbols


def user_risk_limits(user_id: int) -> RiskLimits:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM risk_limits WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return RiskLimits()
    return RiskLimits.from_mapping(
        {
            "enabled": bool(row["enabled"]),
            "max_total_weight": row["max_total_weight"],
            "max_single_weight": row["max_single_weight"],
            "max_positions": row["max_positions"],
            "minimum_cash_ratio": row["minimum_cash_ratio"],
            "max_drawdown": row["max_drawdown"],
            "daily_position_limits": bool(row["daily_position_limits"]),
            "drawdown_action": row["drawdown_action"],
            "drawdown_target_weight": row["drawdown_target_weight"],
        }
    )


def _register_user_strategies(catalog: StrategyCatalog, user_id: int) -> list[str]:
    """把该用户保存在 SQLite 的自定义策略注册进 catalog，返回错误信息列表。"""

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT plugin_name, code FROM user_strategies WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    errors: list[str] = []
    loader = UserStrategyLoader()
    for row in rows:
        try:
            result = loader.load_source(row["code"], label=row["plugin_name"])
        except Exception as exc:  # noqa: BLE001 - 单个策略失败不应阻塞服务
            errors.append(f"{row['plugin_name']}: {exc}")
            continue
        if result.strategies:
            try:
                catalog.register_classes(result.strategies)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{row['plugin_name']}: {exc}")
        for _, message in result.errors:
            errors.append(f"{row['plugin_name']}: {message}")
    return errors


# --------------------------------------------------------------------------- #
# 服务工厂
# --------------------------------------------------------------------------- #


def build_backtest_service(user: dict) -> BacktestService:
    """构造注入了该用户 universe / 自定义策略的回测服务（每请求轻量实例）。"""

    with _backend_cwd():
        catalog = StrategyCatalog()
        service = BacktestService(CONFIG_PATH, strategy_catalog=catalog)

    # 运行期路径全部改为绝对路径，摆脱对启动 CWD 的依赖。
    app_section = service.configs["app"]
    app_section["app"]["runtime_dir"] = str(_abs(app_section["app"]["runtime_dir"]))
    app_section["data"]["repository"] = str(_abs(app_section["data"]["repository"]))

    # 注入该用户的股票池与过滤条件。
    symbols, filters = _user_universe(user["id"])
    if symbols:
        universe_section = service.configs["universe"].setdefault("universe", {})
        universe_section["symbols"] = symbols
        if filters:
            merged = dict(universe_section.get("filters") or {})
            merged.update(filters)
            universe_section["filters"] = merged

    service.user_strategy_errors = tuple(
        (message,) for message in _register_user_strategies(catalog, user["id"])
    )
    return service


def build_factor_registry(user: dict) -> FactorRegistry:
    """内置因子 + Alpha101 因子 + 该用户 SQLite 自定义因子构成的注册表。"""

    registry = FactorRegistry()
    for factor in builtin_factors():
        registry.register(factor)
    for factor in alpha101_factors():
        registry.register(factor)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM custom_factors WHERE user_id = ?", (user["id"],)
        ).fetchall()
    for row in rows:
        try:
            factor = build_custom_factor(
                row["name"],
                display_name=row["display_name"] or "",
                description=row["description"] or "",
                field=row["field"],
                operator=row["operator"],
                window=row["window"],
                window2=row["window2"],
                direction=row["direction"],
            )
        except ValueError:
            continue
        registry.register(factor, replace=True)
    return registry


def build_factor_evaluator() -> FactorEvaluator:
    return FactorEvaluator(market_repository())


def build_data_center_service(user: dict) -> DataCenterService:
    """构造数据中心服务，并把该用户的股票池作为默认更新标的。"""

    with _backend_cwd():
        service = DataCenterService(CONFIG_PATH)
    # 构造完成后替换为绝对路径。
    service.repository = market_repository()
    service.raw_repository = RawDataRepository(RUNTIME_ROOT / "raw")
    service.app["data"]["repository"] = str(MARKET_ROOT)
    service.app["app"]["runtime_dir"] = str(RUNTIME_ROOT)

    symbols, _ = _user_universe(user["id"])
    if symbols:
        service.universe_config.setdefault("universe", {})["symbols"] = symbols
    return service


def available_trading_days(end_date: date | None = None) -> int:
    """本地交易日历中的交易日数量（无日历时返回 0）。"""

    calendar = market_repository().read_table("trade_calendar")
    if calendar.empty:
        return 0
    import pandas as pd

    dates = pd.to_datetime(calendar["cal_date"])
    if end_date is not None:
        dates = dates[dates <= pd.Timestamp(end_date)]
    return int(dates.nunique())
