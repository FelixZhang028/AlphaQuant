"""因子库基础设施：因子定义、上下文与防未来函数约定。

因子统一输出 ``(date, symbol, value)`` 三列的长表，其中：

- ``date``：因子生效日期（t 日收盘后可得）；
- ``symbol``：证券代码；
- ``value``：因子原始值，方向由 ``FactorDefinition.direction`` 描述
  （1 表示值越大预期收益越高，-1 表示值越小预期收益越高）。

防未来函数约定：
- ``compute`` 只能使用 ``bars`` 中每只股票 ``<= 当日`` 的历史数据
  （即只允许 rolling / expanding / 向后 shift 等因果算子）；
- 评估层（``evaluation.FactorEvaluator``）严格用 t 日因子值对应
  t+1 日至 t+N 日的未来收益计算 IC，并可通过截断重算验证因果性。
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository

FACTOR_COLUMNS = ["date", "symbol", "value"]


@dataclass(frozen=True)
class FactorContext:
    """因子计算上下文：封装数据仓库与股票池快照。

    ``as_of`` 为因果性锚点：取数时强制截断到 ``as_of`` 当日（含），
    保证因子计算无法访问未来数据。
    """

    repository: ParquetMarketDataRepository
    symbols: tuple[str, ...] | None = None
    as_of: date | None = None
    start_date: date | None = None

    def bars(self) -> pd.DataFrame:
        """读取 ``<= as_of`` 的日频行情（若未指定 as_of 则读取全部历史）。"""

        return self.repository.get_daily_bars(
            symbols=list(self.symbols) if self.symbols else None,
            start_date=self.start_date,
            end_date=self.as_of,
        )


@dataclass(frozen=True)
class FactorDefinition:
    """因子定义基类：描述元信息并声明 ``compute`` 接口。"""

    name: str = ""
    display_name: str = ""
    description: str = ""
    formula: str = ""
    required_fields: tuple[str, ...] = field(default_factory=tuple)
    min_history: int = 1
    direction: int = 1
    version: str = "1.0.0"
    category: str = "未分类"

    @abstractmethod
    def compute(self, bars: pd.DataFrame) -> pd.DataFrame:
        """根据日频行情计算因子，返回 ``(date, symbol, value)`` 长表。

        ``bars`` 至少包含 ``required_fields`` 声明的列；
        实现必须满足因果性：t 日的因子值只依赖 ``<= t`` 的数据。
        """

    def adjusted_values(self, frame: pd.DataFrame) -> pd.Series:
        """按方向调整后的因子值（乘以 direction），数值越大代表越看好。"""

        return pd.to_numeric(frame["value"], errors="coerce") * self.direction


def melt_wide(wide: pd.DataFrame) -> pd.DataFrame:
    """将 ``index=date, columns=symbol`` 的宽表转为因子标准长表。"""

    long = wide.stack(future_stack=True).rename("value").reset_index()
    long.columns = pd.Index(FACTOR_COLUMNS)
    long = long.dropna(subset=["value"])
    return long.sort_values(["date", "symbol"]).reset_index(drop=True)


def pivot_field(bars: pd.DataFrame, field_name: str) -> pd.DataFrame:
    """把行情长表透视为 ``index=trade_date, columns=symbol`` 的宽表。"""

    frame = bars.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.normalize()
    values = pd.to_numeric(frame[field_name], errors="coerce")
    wide = values.groupby([frame["trade_date"], frame["symbol"]]).last().unstack("symbol")
    return wide.sort_index()
