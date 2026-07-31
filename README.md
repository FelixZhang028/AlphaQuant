# A股个人量化工作台

这是一个运行在本地 Windows 主机上的 A 股日频研究与回测平台。当前版本聚焦：

```text
数据更新
→ 策略信号
→ 目标组合
→ 模拟订单
→ T+1 开盘成交
→ 账户与净值
→ 绩效和成本分析
→ 网页展示
```

当前项目只用于策略研究和模拟，不连接真实券商，不构成投资建议。

## 当前阶段

已经支持：

- 使用 AkShare 更新 A 股证券主表、配置股票池日线和基准指数日线；
- 东方财富连接失败时自动尝试直连，并切换到新浪备用行情接口；
- 保存原始快照、标准化 Parquet 数据、覆盖率报告和数据版本记录；
- 从 `src/quant_platform/strategies` 自动发现策略；
- 在网页中选择策略、修改参数并运行回测；
- T 日收盘生成信号，T+1 开盘模拟成交；
- 处理 A 股 100 股交易单位、佣金、最低佣金、印花税和固定滑点；
- 单独记录参考开盘价、实际模拟成交价和滑点成本；
- 使用 FIFO 还原完整买卖交易并计算净盈亏；
- 计算收益、回撤、交易、成本、换手和持仓集中度指标；
- 保存净值、信号、目标仓位、订单、成交、完整交易、持仓和配置快照；
- 在 Streamlit 中查看数据状态、运行回测和分析历史结果。

目前尚未实现：多因子研究体系、机器学习选股、Qlib、持久化模拟账户、每日自动任务、
完整三级风控、通知、真实券商下单和 ETF 策略。ETF 已按当前开发计划暂缓。

## 普通用户使用现状

当前版本仍然属于“带网页界面的开发者工具”，首次使用需要安装 Python、执行启动命令，
股票池仍需编辑 YAML。完全不懂计算机的用户可能在安装、启动、配置、错误处理和回测
指标理解方面遇到困难。

后续产品化方向包括：

- Windows 双击启动脚本或安装程序；
- 首次使用向导；
- 在网页中管理股票池和常用设置；
- 基础模式与专业模式；
- 数据是否可回测的自动检查；
- 策略参数和回测指标的中文解释；
- 中文错误提示、重试和诊断信息；
- 一键导出回测报告。

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

可以通过以下参数跳过某一类数据：

```text
--skip-security-master
--skip-market
--skip-benchmark
```

### 3. 启动网页

```powershell
python -m streamlit run src/quant_platform/web/app.py
```

启动后一般访问：

```text
http://localhost:8501
```

网页中的主要功能：

- **A股量化工作台**：选择策略、修改参数、运行回测并查看绩效；
- **数据管理**：更新行情、查看覆盖率、证券主表、基准行情和数据版本；
- **回测结果**：查看概览、收益与风险、交易与成本、持仓分析和订单明细。

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

详细说明见 `docs/data_center.md`。

## 当前策略与回测规则

内置策略为 `a_share_momentum`，配置文件位于
`configs/strategies/momentum.yaml`。主要逻辑：

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

## 回测指标

新回测提供以下指标：

### 收益与风险

- 累计收益、年化收益；
- 年化波动率、下行波动率；
- Sharpe、Sortino、Calmar；
- 最大回撤及峰值、谷底、恢复日期；
- 最大回撤持续交易日；
- 最佳和最差单日收益；
- 正收益日比例和正收益月比例；
- 月度收益表和回撤曲线。

### 交易与成本

- 订单数、成交数、拒单数和订单成交率；
- FIFO 完整交易数、胜率、平均盈亏、盈亏比和 Profit Factor；
- 平均和最大持仓天数；
- 区间换手率和年化换手率；
- 佣金、印花税、滑点成本和总交易成本；
- 成交金额、已实现毛盈亏和已实现净盈亏。

### 持仓

- 平均和最大持仓数量；
- 平均和最大仓位；
- 平均和最低现金比例；
- 在场时间比例；
- 单股最大权重；
- 平均和最大持仓集中度 HHI。

指标口径、公式和边界见 `docs/backtest_metrics.md`。基准数据稳定后再增加超额收益、
信息比率、Alpha 和 Beta。

## 新增自己的策略

在 `src/quant_platform/strategies` 新建 `.py` 文件并实现 `Strategy`：

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
            "lookback", "观察窗口", ParameterKind.INTEGER, 20,
            minimum=2, maximum=250,
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
            fields=["adjusted_close"], lookback=self.lookback
        )
        return []
```

不需要修改 `plugins.py`、命令行或网页。平台会自动发现策略，并根据
`StrategyParameter` 生成网页参数控件。

策略应遵守：

- 只能通过 `StrategyContext` 读取截至当前信号日的数据；
- 不直接调用 AkShare 或读写本地文件；
- 只输出信号，不直接生成订单或修改账户；
- 组合、风控、订单、成交和账户由平台负责。

## 运行结果

每次新回测保存在 `runtime/runs/<run_id>/`：

```text
nav.parquet
signals.parquet
target_positions.parquet
orders.parquet
fills.parquet
closed_trades.parquet
positions.parquet
summary.json
config.snapshot.yaml
```

`closed_trades.parquet` 保存 FIFO 买卖配对、参考价格、成交价格、费用、滑点、
净盈亏和持仓天数。旧回测仍可打开，但旧文件不存在的指标会显示为 `—`。

这些目录属于本地运行数据，默认不会提交到 Git。

## 示例数据

不希望联网时，可以使用确定性示例数据：

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

当前有 23 个自动化测试，覆盖配置、数据标准化、AkShare 网络回退、数据中心、
策略发现、防未来数据访问、订单、滑点、FIFO完整交易、绩效指标、账户和完整回测流程。

## 项目结构

```text
configs/                         YAML 配置
docs/                            设计、数据和指标文档
scripts/                         常用命令入口
src/quant_platform/
  application/                   数据与回测用例服务
  accounts/                      账户和持仓
  backtest/                      回测引擎、交易还原和指标
  core/                          配置、日志、注册器和异常
  data/                          数据源、标准化、质量和存储
  execution/                     订单、滑点和 T+1 模拟成交
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
- 改成 `reject_trade` 会更保守，但状态数据补全前可能拒绝大部分订单；
- 当前滑点是配置假设，不是由真实成交数据校准；
- 日频回测无法还原盘口排队、撮合延迟和真实市场冲击；
- 基准行情尚未计入超额收益和信息比率；
- 当前只有固定股票池的 A 股动量策略和等权组合；
- 当前风控只有基础权重检查，还没有配置界面和可审计风控事件；
- 账户只存在于单次历史回测中，不能作为每日持续运行的模拟账户；
- 没有任务调度、通知、因子研究、模型训练和真实交易接口；
- 普通用户仍需安装 Python、执行命令并编辑 YAML。

因此，当前结果适合工程验证和策略原型研究，不适合作为实盘决策的唯一依据。

## 后续路线

按当前计划：

1. 实现可配置、可审计的风控引擎；
2. 增加回测风控参数界面和风控结果标签页；
3. 实现批量参数回测和实验对比；
4. 增加基础模式、首次使用向导和一键启动；
5. 后续使用更完整的付费数据补全交易状态和基准；
6. 后续研究更多策略，再考虑多因子、Qlib和机器学习；
7. 最后实现持久化模拟账户、每日任务和通知。

## 安全说明

- AkShare 不需要 Token；
- 不要把 Tushare Token、邮箱密码或代理密码写入配置并提交 Git；
- `.env`、本地行情、模型和回测结果已配置为忽略；
- 平台不会连接或操作真实券商账户。
