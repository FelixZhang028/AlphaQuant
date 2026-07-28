# A股个人量化工作台

这是一个运行在本地 Windows 主机上的 A 股日频研究与回测平台。当前版本聚焦
“数据更新 → 策略信号 → 目标组合 → 模拟订单 → T+1 成交 → 账户净值 → 网页展示”
这一条最小闭环。

当前项目只用于策略研究和模拟，不连接真实券商，不构成投资建议。

## 当前阶段

已经支持：

- 使用 AkShare 更新 A 股证券主表、配置股票池日线和基准指数日线；
- 东方财富连接失败时自动尝试直连，并切换到新浪备用行情接口；
- 保存原始快照、标准化 Parquet 数据、覆盖率报告和数据版本记录；
- 从 `src/quant_platform/strategies` 自动发现策略；
- 在网页中选择策略、修改参数并运行回测；
- T 日收盘生成信号，T+1 开盘模拟成交；
- 处理 A 股 100 股交易单位、佣金、最低佣金、印花税和滑点；
- 保存净值、信号、目标仓位、订单、成交、持仓和回测配置快照；
- 在 Streamlit 中查看数据状态、运行回测和浏览历史结果。

目前尚未实现：多因子研究体系、机器学习选股、Qlib、持久化模拟账户、每日自动任务、
三级风控、通知、真实券商下单和 ETF 策略。ETF 已按当前开发计划暂缓。

## 环境要求

- Windows 10/11；
- Python 3.11 或 3.12；
- 能访问 AkShare 所依赖的公开行情网站。

安装项目及开发依赖：

```powershell
python -m pip install -e ".[dev]"
```

当前使用 AkShare 不需要 Token。Tushare 仅保留为可选适配器；有权限时再安装：

```powershell
python -m pip install -e ".[tushare]"
```

## 快速开始

### 1. 配置股票池

编辑 `configs/universes/a_share_demo.yaml`：

```yaml
universe:
  id: a_share_demo
  symbols:
    - 600519.SH
    - 000001.SZ
  filters:
    exclude_st: true
    exclude_suspended: true
    minimum_listing_days: 120
    minimum_history_days: 61
    minimum_average_amount: 20000000
```

数据更新默认只下载这里配置的股票，不会下载全市场所有股票的历史行情。

### 2. 更新数据

推荐在网页的数据管理页面操作，也可以运行：

```powershell
python scripts/update_data.py `
  --start-date 20220101 `
  --end-date 20251231
```

查看本地数据范围、覆盖率和异常状态：

```powershell
python scripts/data_status.py
```

如只想更新部分数据，可以使用：

```text
--skip-security-master
--skip-market
--skip-benchmark
```

### 3. 启动网页

```powershell
streamlit run src/quant_platform/web/app.py
```

浏览器中的主要页面：

- **A股量化工作台**：选择策略、修改参数、运行回测、查看净值与交易记录；
- **数据管理**：更新行情、查看覆盖率、证券主表、基准行情和数据版本。

### 4. 命令行回测

使用当前配置运行回测：

```powershell
python scripts/run_backtest.py
```

临时指定日期和初始资金：

```powershell
python scripts/run_backtest.py `
  --start-date 20230103 `
  --end-date 20241231 `
  --initial-cash 1000000
```

查看平台自动发现的策略：

```powershell
python -m quant_platform.cli strategies
```

## 数据流程

```text
AkShare
  → 东方财富接口
  → 代理失败时自动直连
  → 东方财富仍不可用时切换新浪接口
  → 原始数据快照
  → 字段与单位标准化
  → 数据质量检查
  → 本地 Parquet
  → 覆盖率与版本记录
```

数据中心维护三个主要数据集：

| 数据集 | 内容 |
|---|---|
| `security_master` | 当前沪深京 A 股证券列表 |
| `daily_bars` | 配置股票池的未复权和前复权日线 |
| `benchmark_bars` | `configs/app.yaml` 中配置的基准指数日线 |

策略常用的标准行情字段包括：

| 字段 | 含义 |
|---|---|
| `symbol` | 标准代码，例如 `600519.SH` |
| `trade_date` | 交易日期 |
| `raw_open/high/low/close` | 未复权开高低收 |
| `adjusted_close` | 前复权收盘价 |
| `adj_factor` | 当前数据推导出的复权比例 |
| `volume` | 成交量，单位为股 |
| `amount` | 成交额，单位为元 |
| `is_suspended` | 是否停牌 |
| `is_st` | 是否 ST |
| `up_limit/down_limit` | 涨跌停价格 |
| `quality_status` | 数据质量与交易状态 |

每次更新都会在 `data_manifests` 中记录版本号、数据源、请求参数、日期范围、行数、
证券数量、质量摘要和错误信息。单个数据集失败不会中断其他数据集更新。

更详细的数据中心说明见 `docs/data_center.md`。

## 当前策略与回测规则

内置策略为 `a_share_momentum`，配置文件位于
`configs/strategies/momentum.yaml`。主要逻辑是：

1. 过滤长期动量为负的股票；
2. 过滤最近 20 日平均成交额不足的股票；
3. 按短期动量从高到低排序；
4. 选择 Top N；
5. 等权构建目标组合；
6. 在下一个交易日开盘执行。

网页可以直接修改：

- 短期和长期动量窗口；
- 最低平均成交额；
- 回测日期；
- 初始资金；
- 最大持仓数量；
- 日、周、月调仓频率。

当前回测评价指标包括累计收益、年化收益、年化波动率、Sharpe 和最大回撤，
同时记录成交数量、拒单数量、佣金和印花税。

## 新增自己的策略

在 `src/quant_platform/strategies` 新建一个 `.py` 文件，实现 `Strategy`：

```python
from typing import Any, ClassVar

from quant_platform.signals.models import Signal
from quant_platform.strategies.base import Strategy
from quant_platform.strategies.context import StrategyContext
from quant_platform.strategies.spec import ParameterKind, StrategyParameter


class MyStrategy(Strategy):
    plugin_name = "my_strategy"
    display_name = "我的策略"
    description = "策略说明"
    parameters: ClassVar[tuple[StrategyParameter, ...]] = (
        StrategyParameter(
            "lookback",
            "观察窗口",
            ParameterKind.INTEGER,
            20,
            minimum=2,
            maximum=250,
        ),
    )
    required_fields = frozenset(
        {"symbol", "trade_date", "adjusted_close"}
    )

    def __init__(self, strategy_id: str, lookback: int) -> None:
        self.strategy_id = strategy_id
        self.lookback = lookback

    @classmethod
    def from_parameters(
        cls, strategy_id: str, parameters: dict[str, Any]
    ) -> "MyStrategy":
        return cls(strategy_id, int(parameters["lookback"]))

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        history = context.history(
            fields=["adjusted_close"],
            lookback=self.lookback,
        )
        # 在这里计算信号并返回 list[Signal]
        return []
```

不需要修改 `plugins.py`、命令行或网页。平台会自动发现策略，并根据
`StrategyParameter` 生成网页参数控件。

策略应遵守以下边界：

- 只能通过 `StrategyContext` 读取截至当前信号日的数据；
- 不直接调用 AkShare 或读取本地文件；
- 只输出信号，不直接生成订单或修改账户；
- 组合、风控、订单、成交和账户由平台负责。

## 运行结果

每次回测保存在 `runtime/runs/<run_id>/`：

```text
nav.parquet
signals.parquet
target_positions.parquet
orders.parquet
fills.parquet
positions.parquet
summary.json
config.snapshot.yaml
```

这些目录属于本地运行数据，默认不会提交到 Git。

## 示例数据

如果暂时不希望联网，可以使用确定性示例数据：

```powershell
python -m quant_platform.cli sample-data --config configs/app.sample.yaml
python -m quant_platform.cli backtest --config configs/app.sample.yaml
```

## 测试与代码检查

```powershell
python -m pytest -q
python -m compileall -q src tests
python -m ruff check .
python -m mypy src
```

当前测试覆盖配置、数据标准化、AkShare 网络回退、数据中心、策略发现、
防未来数据访问、订单、成交、账户和完整回测流程。

## 项目结构

```text
configs/                         YAML 配置
docs/                            设计和使用文档
scripts/                         常用命令入口
src/quant_platform/
  application/                   数据与回测用例服务
  accounts/                      账户和持仓
  backtest/                      回测引擎与指标
  core/                          配置、日志、注册器和异常
  data/                          数据源、标准化、质量和存储
  execution/                     订单与 T+1 模拟成交
  portfolio/                     组合构建
  risk/                          基础风控
  signals/                       信号模型
  strategies/                    策略插件
  universe/                      股票池
  web/                           Streamlit 页面
tests/                           单元和集成测试
runtime/                         本地数据与运行结果
```

## 已知限制

- 股票池还是配置文件中的固定列表，尚不支持历史时点指数成分股；
- AkShare 免费数据不能稳定提供完整的历史 ST、停牌和涨跌停状态；
- 当前大量行情可能标记为 `UNKNOWN_STATUS`；
- `unknown_status_policy: allow_trade` 适合跑通工程流程，但可能低估无法成交；
- 改成 `reject_trade` 会更保守，但在状态数据补全前可能拒绝大部分订单；
- 基准行情可以下载和展示，但尚未计入超额收益、信息比率等回测指标；
- 当前只有固定股票池的 A 股动量策略和等权组合；
- 账户只存在于单次历史回测中，尚不能作为每日持续运行的模拟账户；
- 没有任务调度、通知、因子研究、模型训练和真实交易接口。

因此，当前结果适合工程验证和策略原型研究，不适合作为实盘决策的唯一依据。

## 后续路线

按当前 A 股优先的方向，建议依次完成：

1. 补全基准、交易日历、ST、停牌和涨跌停数据；
2. 增加基准收益、超额收益、信息比率、换手率和胜率；
3. 实现因子插件、因子评价和多因子选股；
4. 实现持久化模拟账户、每日任务和订单人工确认；
5. 完善资产级、策略级和总组合级风控；
6. 最后接入 Qlib 和机器学习模型。

## 安全说明

- AkShare 不需要 Token；
- 不要把 Tushare Token、邮箱密码或代理密码写入配置并提交 Git；
- `.env`、本地行情、模型和回测结果已配置为忽略；
- 平台不会连接或操作真实券商账户。
