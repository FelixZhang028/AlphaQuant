## 摘要

本次 PR 围绕性能、可扩展性和可维护性做四类改动：

1. 回测引擎主循环去 O(n²) 热点
2. 账户引擎去掉每日峰值重算和 deepcopy
3. daily_bars 改为按年分区存储，支持增量写入和谓词下推
4. 拆分 DataCenterService，并统一 CLI 入口

## 改动详情

### 1. 回测引擎性能优化

`src/quant_platform/backtest/engine.py`

- 行情按 `trade_date` 预分组为 `dict[date, DataFrame]`，避免每个交易日全表布尔过滤。
- 历史切片改为 `searchsorted` + `iloc` 连续切片，不再每个调仓日复制整段历史。
- `closing_prices` 由 `iterrows()` 改为向量化实现。
- 新增 `_history_through` 辅助方法。

### 2. 账户引擎热点优化

`src/quant_platform/accounts/account.py`

- `mark_to_market` 维护 `self._peak_equity`，消除每天遍历全部历史快照的 O(n²) 峰值计算。
- `apply_fill` 去掉每次成交的 `deepcopy(self.positions)`，改为浅拷贝 + 仅复制受影响持仓。

### 3. daily_bars 按年分区

`src/quant_platform/data/repositories/parquet_repository.py`

- `daily_bars` 改为 `<root>/daily_bars/year=YYYY/data.parquet` 分区存储。
- `save_table("daily_bars", ...)` 只读写受影响年份分区，不再全表重写。
- `get_daily_bars` 使用 pyarrow 谓词下推按年读取。
- 兼容旧单文件格式：读取自动回退，下次写入自动迁移。
- 修复 `readiness_service.py` 中硬编码旧路径的问题。

### 4. 架构拆分与 CLI 统一

- 新增 `application/data_source_resolver.py`：集中数据源解析、环境加载、provider 构建。
- 新增 `application/manifest_summary.py`：抽取 manifest 路由摘要逻辑。
- 精简 `application/data_service.py`，保留兼容的薄委托方法。
- 统一 `cli.py` 入口，新增 `status` / `update` 子命令，删除孤儿模块 `data_cli.py`。
- 更新 `scripts/` 和 `docs/data_center.md` 中相关命令。

## 验证

- `python -m pytest -q --no-header`：`84 passed`
- `ruff check src tests scripts`：`All checks passed!`
- CLI：
  - `python -m quant_platform.cli --help`
  - `python -m quant_platform.cli status --config configs/app.sample.yaml`

## 迁移说明

`daily_bars` 的磁盘格式由单文件改为按年分区。对已有本地数据：

- 读取：无需任何操作，自动回退旧格式。
- 写入：下次更新行情时会自动迁移旧单文件到分区格式并删除旧文件。

## 已知未包含（不在本次范围）

- 全仓库仍有部分历史文件未 `ruff format`，本次只格式化改动文件。
- `mypy` 存在既有报错（缺少 `types-PyYAML`、`analytics.py` 一个类型问题、`baostock_provider.py` 一个 lambda 推断），与本次改动无关。

## 需要重点 review 的地方

- `parquet_repository.py` 的分区读写和旧格式迁移逻辑。
- `data_service.py` 拆分后的职责边界和兼容方法。
- 回测引擎的 `searchsorted` 历史切片是否有边界遗漏。
