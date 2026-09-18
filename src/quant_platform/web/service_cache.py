"""Streamlit 页面共享的 service 单例与数据缓存。

规则：
- 仓储 / service 对象用模块级 ``lru_cache`` 单例，绝不放进 ``st.cache_data``
  ——缓存的是序列化后的 DataFrame，缓存对象本身会破坏仓储状态；
- DataFrame 结果用 ``st.cache_data(ttl=600)``，以最近一次成功数据版本的
  ``completed_at`` 作为指纹参数：数据更新后指纹变化，缓存自动失效，
  比手动 clear 可靠；TTL 只作为兜底过期。
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from quant_platform.application.backtest_service import BacktestService
from quant_platform.application.data_service import DataCenterOverview, DataCenterService
from quant_platform.core.config import load_yaml, require_mapping
from quant_platform.data.network import friendly_data_error
from quant_platform.data.repositories.parquet_repository import (
    ParquetMarketDataRepository,
)
from quant_platform.data.versioning import latest_successful_manifest

DEFAULT_CONFIG_PATH = "configs/app.yaml"


@lru_cache(maxsize=4)
def _data_center_at(config_path: str, working_directory: str) -> DataCenterService:
    """数据中心 service 的进程级单例。"""

    return DataCenterService(config_path)


@lru_cache(maxsize=4)
def _backtest_at(config_path: str, working_directory: str) -> BacktestService:
    """回测 service 的进程级单例。"""

    return BacktestService(config_path)


@lru_cache(maxsize=4)
def _data_repository_at(resolved_root: str) -> ParquetMarketDataRepository:
    return ParquetMarketDataRepository(resolved_root)


def get_data_center_service(config_path: str = DEFAULT_CONFIG_PATH) -> DataCenterService:
    return _data_center_at(str(Path(config_path).resolve()), str(Path.cwd()))


def get_backtest_service(config_path: str = DEFAULT_CONFIG_PATH) -> BacktestService:
    return _backtest_at(str(Path(config_path).resolve()), str(Path.cwd()))


def get_data_repository(config_path: str = DEFAULT_CONFIG_PATH) -> ParquetMarketDataRepository:
    """市场数据仓储单例。

    直接从 ``data.repository`` 构造：只读行情的页面（因子实验室等）
    不应被要求提供完整数据中心配置（``app`` / ``universe`` 等段），
    最小 ``data`` 配置即可工作。仓储本身无状态，与数据中心持有的
    实例指向同一目录，行为一致。仓储及行情缓存键均为绝对仓储路径，
    service 和概览缓存则同时区分绝对配置路径与构造时的工作目录。
    """

    config = load_yaml(Path(config_path).resolve())
    root = Path(require_mapping(config, "data")["repository"]).resolve()
    return _data_repository_at(str(root))


def data_fingerprint(repository: ParquetMarketDataRepository) -> str:
    """最近一次成功数据版本的完成时间，作为缓存失效指纹。"""

    parts: list[str] = []
    datasets = (
        "daily_bars",
        "benchmark_bars",
        "security_master",
        "corporate_actions",
        "universe_membership",
        "delisting_settlements",
    )
    for dataset in datasets:
        manifest = latest_successful_manifest(repository, dataset)
        if manifest:
            stamp = manifest.get("completed_at") or manifest.get("version_id") or ""
            parts.append(f"{dataset}:{stamp}")
    return "|".join(parts) if parts else "no-successful-manifest"


@st.cache_data(ttl=600)
def _overview_at(
    config_path: str, working_directory: str, repo_fingerprint: str
) -> DataCenterOverview:
    """数据中心概览（一次全量读 5 张表），按指纹 + TTL 缓存。"""

    return _data_center_at(config_path, working_directory).overview()


@st.cache_data(ttl=600)
def _coverage_at(repository_root: str, repo_fingerprint: str) -> pd.DataFrame:
    """页面级全量日线行情（覆盖率检查 / 导出筛选），按指纹 + TTL 缓存。"""

    return _data_repository_at(repository_root).read_table("daily_bars")


@st.cache_data(ttl=600)
def _closed_loop_at(
    config_path: str, working_directory: str, repo_fingerprint: str
) -> dict[str, Any]:
    """全市场闭环状态（一次读多张表），按指纹 + TTL 缓存。"""

    return _data_center_at(config_path, working_directory).closed_loop_status()


def get_closed_loop_status(config_path: str, repo_fingerprint: str) -> dict[str, Any]:
    return _closed_loop_at(
        str(Path(config_path).resolve()), str(Path.cwd()), repo_fingerprint
    )


def get_data_overview(config_path: str, repo_fingerprint: str) -> DataCenterOverview:
    return _overview_at(str(Path(config_path).resolve()), str(Path.cwd()), repo_fingerprint)


def get_coverage_bars(config_path: str, repo_fingerprint: str) -> pd.DataFrame:
    return _coverage_at(str(get_data_repository(config_path).root), repo_fingerprint)


def service_or_stop(
    factory: Callable[[str], Any],
    error_message: str,
    config_path: str = DEFAULT_CONFIG_PATH,
) -> Any:
    """统一的页面级 service 初始化样板：单例 + 失败提示 + 停止渲染。"""

    try:
        return factory(config_path)
    except Exception as exc:  # noqa: BLE001 - 页面初始化必须给出可读提示
        st.error(f"{error_message}：{friendly_data_error(exc)}")
        st.stop()


def cached_overview_or_stop(
    config_path: str = DEFAULT_CONFIG_PATH,
) -> tuple[DataCenterService, DataCenterOverview]:
    """单例 service + 缓存概览，失败时提示并停止渲染。"""

    service = service_or_stop(get_data_center_service, "数据中心加载失败", config_path)
    try:
        overview = get_data_overview(config_path, data_fingerprint(service.repository))
    except Exception as exc:  # noqa: BLE001 - 数据损坏时给出可读提示
        st.error(f"数据中心加载失败：{friendly_data_error(exc)}")
        st.stop()
    return service, overview
