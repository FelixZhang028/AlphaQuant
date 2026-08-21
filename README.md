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

- 使用 iFinD（优先）或 AkShare（自动回退）更新股票池日线，证券主表与基准指数由 AkShare 更新；
- 可在数据管理页面为本次日线更新指定首选来源，并选择是否允许自动回退；
- 东方财富连接失败时自动尝试直连，并切换到新浪备用行情接口；
- 保存原始快照、标准化 Parquet 数据、覆盖率报告和数据版本记录；
- 从 `src/quant_platform/strategies` 自动发现策略；
- 在网页中选择策略、修改参数并运行回测；
- 在网页中编写或上传 Python 策略，继承 `BaseStrategy` 并注册后直接回测；
- T 日收盘生成信号，T+1 开盘模拟成交；
- 处理 A 股 100 股交易单位、佣金、最低佣金、印花税和固定滑点；
- 单独记录参考开盘价、实际模拟成交价和滑点成本；
- 使用 FIFO 还原完整买卖交易并计算净盈亏；
- 计算收益、回撤、交易、成本、换手和持仓集中度指标；
- 保存净值、信号、目标仓位、订单、成交、完整交易、持仓和配置快照；
- 在 Streamlit 中查看数据状态、运行回测和分析历史结果；
- 批量运行最多100组参数组合，按收益、Sharpe、Calmar或回撤排序；
- 使用滚动训练窗口选择参数，并只在随后未见过的样本外区间评价；
- 回测前检查时间轴，异常断档会直接阻止生成误导性绩效指标；
- 选择2～5次历史回测，对比指标和标准化净值曲线；
- 使用统一风控配置检查总仓位、单股权重、持股数量、现金比例和回撤停止线；
- 每日检查实际持仓漂移，并可在回撤触线后停止开仓、降低仓位或清仓；
- 在结果顶部显示“有效 / 有警告 / 无效”以及具体可信度说明；
- 保存每次风控检查、运行状态以及失败原因；
- 创建本地日线模拟账户，并按指定日期推进；
- 在数据管理页面按股票和日期筛选、预览并下载完整日线行情 CSV；
- 通过中文界面添加、搜索、移除股票并调整股票池过滤条件；
- 首次使用页自动检查配置、股票池、历史天数、基准行情和数据质量；
- 提供 Windows 首次安装和日常双击启动脚本。

目前尚未实现：多因子研究体系、机器学习选股、Qlib、实时行情驱动的增量模拟交易、
每日自动任务、通知、真实券商下单和 ETF 策略。ETF 已按当前开发计划暂缓。

## 普通用户使用现状

当前版本已经不要求普通用户执行启动命令或编辑股票池 YAML：

- 首次使用只需安装 Python，然后双击 `install_and_start.bat`；
- 后续双击 `start.bat` 即可打开网页；
- “开始使用”页面会自动检查是否具备回测条件；
- 股票池可以在网页中按代码添加、按名称搜索、移除和调整过滤条件；
- 新增股票后，向导会提示前往数据管理补充行情。

仍可继续优化的体验包括基础模式与专业模式、策略和指标解释、失败任务重试、
诊断信息以及一键导出中文回测报告。

## 环境要求

- Windows 10/11；
- Python 3.11 或 3.12；
- 能访问 AkShare 所依赖的公开行情网站。

开发者如需运行测试和代码检查，可以安装开发依赖：

```powershell
python -m pip install -e ".[dev]"
```

AkShare 不需要 Token。iFinD 需要官方 Windows SDK 和账号权限；Tushare 仅保留为可选适配器：

```powershell
python -m pip install -e ".[tushare]"
```

## 快速开始

### 1. 首次安装并启动

先安装 Python 3.11 或 3.12，并在 Python 安装界面勾选“Add Python to PATH”。

第一次使用时，双击项目根目录中的：

```text
install_and_start.bat
```

脚本会自动创建独立的 `.venv` 环境、安装项目依赖并打开浏览器。以后使用时只需双击：

```text
start.bat
```

如果已经配置好 Python 环境，也可以继续使用命令行：

```powershell
python -m streamlit run src/quant_platform/web/app.py
```

### 2. 按向导设置股票池

首次数据尚未准备好时，平台默认打开“开始使用”页面。按顺序进入“股票池管理”：

- 输入六位股票代码，系统会自动判断上海、深圳或北京交易所；
- 也支持 `600519.SH`、`SH600519` 等格式；
- 更新证券主表后，可以按股票名称搜索；
- 移除股票不会删除已经下载的本地历史行情；
- 保存后，数据更新和新回测会自动使用最新股票池。

股票池仍保存在 `configs/universes/a_share_demo.yaml`，高级用户可以继续直接编辑。

### 3. 准备数据并检查回测条件

进入“数据管理”，选择日期范围并更新证券主表、配置股票池行情和基准行情。
返回“开始使用”后，系统会自动检查：

- 配置和默认策略能否加载；
- 股票池是否为空；
- 每只股票是否达到最少历史交易日；
- 证券主表和基准行情是否存在；
- 是否有重复行情或关键价格缺失。

检查通过后即可进入“单次回测与复盘”。高级用户也可以运行：

```powershell
python scripts/update_data.py `
  --start-date 20220101 `
  --end-date 20251231
```

网页中的主要功能：

- **开始使用**：自动检查股票池和本地数据，并提示下一步操作；
- **单次回测与复盘**：选择策略和一组确定参数，运行回测并深入查看绩效、交易与持仓；
- **数据管理**：更新行情、查看覆盖率，并下载日线行情 CSV；
- **股票池管理**：添加、搜索、移除股票并调整过滤条件；
- **参数优化与稳健性验证**：从成功回测继承配置，进行网格优化和滚动样本外验证；
- **回测记录库**：筛选、追溯并比较2～5次历史回测；
- **风险管理**：设置每日持仓纠偏及回撤处理动作，查看最近风控记录；
- **模拟交易**：创建本地日线模拟账户，并把账户推进到指定日期。

### 4. 使用参数验证、风控和模拟交易

先在“单次回测与复盘”完成一个基准回测，再点击“用本次结果创建验证实验”。
参数优化的候选值使用逗号分隔，例如：

```text
短期窗口：10,20,40
长期窗口：60,120
```

上面的示例会运行6种组合。单次最多100组，避免误操作导致等待时间过长。优化结果保存在
`runtime/optimizations/<optimization_id>/results.csv`，每个参数组合仍会生成独立回测目录。

全局风控配置保存在 `configs/risk.yaml`。界面修改后只影响新运行的回测和模拟账户，不会
修改已经完成的历史结果。系统每日收盘后检查实际持仓；达到回撤线后可以选择停止新开仓、
降低至指定仓位或清仓，纠偏订单在下一交易日开盘执行。

“滚动样本外验证”会在每个训练窗口中选择参数，再将入选参数用于紧随其后的测试窗口。
结果保存在 `runtime/walk_forward/<validation_id>`，其中包含每个窗口的参数和样本外指标。

模拟账户保存在 `runtime/paper_accounts/<account_id>/account.json`。当前是日线回放模式：
每次推进会使用固定的账户配置从开始日期重新计算到目标日期，适合验证策略和平台流程，
不代表实时盘口撮合。

### 5. 命令行回测

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
iFinD 日线行情
  → 失败时自动回退 AkShare
  → AkShare 代理失败时自动直连
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

详细说明见 `docs/data_center.md`；iFinD 配置与数据口径见
`docs/ifind_data_source.md`。

## 当前策略与回测规则

新手可以从"零代码策略工作台"选择六种模板和保守、均衡、激进预设，或使用积木编辑器组合白名单指标，无需编写 Python。详细说明见 `docs/zero_code_strategy.md`。

有基础的用户可以在"自定义策略（Python）"页面编写或上传 `.py` 策略，继承 `BaseStrategy` 并注册后直接回测，参数由 `__init__` 签名自动生成表单。详细说明见 `docs/custom_strategy.md`。

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

推荐方式：在网页"自定义策略（Python）"中编写或上传策略，继承 `BaseStrategy` 并注册即可，无需改动源码。详细说明见 `docs/custom_strategy.md`。

如需内置为平台插件，也可在 `src/quant_platform/strategies` 新建 `.py` 文件并实现 `Strategy`：

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
risk_events.parquet
summary.json
config.snapshot.yaml
run.json
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

当前有 94 个自动化测试，覆盖配置、数据标准化、AkShare 网络回退、数据中心、
策略发现、自定义策略加载与注册、防未来数据访问、订单生命周期、滑点、FIFO完整交易、
绩效指标、风控、运行状态、参数优化、模拟账户和完整回测流程。

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

- 股票池可以通过界面维护，但仍是固定列表，尚不支持历史时点指数成分股；
- AkShare 免费数据不能稳定提供完整的历史 ST、停牌和涨跌停状态；
- 当前大量行情可能标记为 `UNKNOWN_STATUS`；
- 默认使用 `unknown_status_policy: reject_trade`，未知状态股票不会进入候选池，
  未知状态订单也不会成交；
- 回测区间存在未知交易状态时，结果会保存为诊断材料，但绩效指标标记为不可用于策略评价；
- 没有当前审计版本号的历史结果统一标记为“旧版未验证”，不能用于参数优化和模拟账户；
- 当前滑点是配置假设，不是由真实成交数据校准；
- 日频回测无法还原盘口排队、撮合延迟和真实市场冲击；
- 基准行情尚未计入超额收益和信息比率；
- 当前只有固定股票池的 A 股动量策略和等权组合；
- 已支持每日实际持仓纠偏和回撤处置，但还没有委托频率、每日成交上限和实盘紧急撤单；
- 当前模拟账户采用历史日线回放，不接收实时行情，也不会连接券商；
- 模拟账户每次推进会重新计算历史，数据或策略代码变化时结果也可能变化；
- 没有任务调度、通知、因子研究、模型训练和真实交易接口；
- 普通用户首次使用仍需安装 Python，后续可以通过双击脚本和网页操作。

因此，当前结果适合工程验证和策略原型研究，不适合作为实盘决策的唯一依据。

## 后续路线

按当前计划：

1. 继续补充订单金额、每日成交量、委托频率和紧急停止等实盘级风控；
2. 将回放式模拟账户升级为增量运行，并增加每日自动任务和通知；
3. 在现有滚动样本外验证上继续增加参数稳定性热力图和压力测试；
4. 增加基础模式、专业模式和一键导出中文回测报告；
5. 后续使用更完整的付费数据补全交易状态和基准；
6. 后续研究更多策略，再考虑多因子、Qlib和机器学习；
7. 最后通过独立适配器连接 vn.py 或券商交易接口。

## 安全说明

- AkShare 不需要 Token；
- 不要把 Tushare Token、邮箱密码或代理密码写入配置并提交 Git；
- `.env`、本地行情、模型和回测结果已配置为忽略；
- 平台不会连接或操作真实券商账户。
