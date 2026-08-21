# 自定义策略（Python）

面向有一定基础的用户：无需改动平台源码，即可在网页上编写或上传 `.py` 策略文件，
继承 `BaseStrategy` 并注册后，平台会自动识别策略、生成参数表单并直接回测。

## 快速上手

在「自定义策略（Python）」页面选择「编写策略」，或上传一个 `.py` 文件。最小示例：

```python
import pandas as pd

from quant_platform.signals.models import Signal
from quant_platform.strategies.context import StrategyContext
from quant_platform.user_strategies import BaseStrategy, register_strategy


@register_strategy(
    "my_ma_momentum",
    display_name="我的双均线动量",
    description="价格站上快线且快线高于慢线时，按近期动量排序选股",
)
class MyStrategy(BaseStrategy):
    required_fields = frozenset({"symbol", "trade_date", "adjusted_close", "amount"})

    # 可选：给参数更友好的标签、范围与说明
    param_specs = {
        "fast": {"label": "快速均线（日）", "min": 2, "max": 60},
        "slow": {"label": "慢速均线（日）", "min": 5, "max": 250},
        "momentum": {"label": "动量窗口（日）", "min": 2, "max": 120},
    }

    def __init__(self, fast: int = 5, slow: int = 20, momentum: int = 20):
        self.fast = fast
        self.slow = slow
        self.momentum = momentum

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        history = context.history(
            fields=["adjusted_close", "amount"],
            lookback=max(self.slow, self.momentum) + 1,
        )
        signals: list[Signal] = []
        cutoff = pd.Timestamp(context.trade_date)
        for symbol, group in history.groupby("symbol"):
            group = group.sort_values("trade_date")
            if group.empty or pd.Timestamp(group.iloc[-1]["trade_date"]) != cutoff:
                continue
            close = pd.to_numeric(group["adjusted_close"], errors="coerce").dropna()
            if len(close) < self.slow + 1:
                continue
            fast_ma = float(close.tail(self.fast).mean())
            slow_ma = float(close.tail(self.slow).mean())
            current = float(close.iloc[-1])
            if not (current > fast_ma > slow_ma):
                continue
            base = float(close.iloc[-self.momentum - 1])
            if base <= 0:
                continue
            signals.append(
                Signal(
                    strategy_id=self.strategy_id,
                    trade_date=context.trade_date,
                    symbol=str(symbol),
                    signal_type="MY_MA_MOMENTUM",
                    score=current / base - 1.0,
                )
            )
        return sorted(signals, key=lambda signal: -signal.score)
```

## 基类接口

`BaseStrategy` 继承内置的 `Strategy`，与回测引擎、策略目录天然兼容。子类只需：

1. 用 `@register_strategy("唯一英文标识")` 注册；
2. 在 `__init__` 中声明**带默认值**的关键字参数；
3. 重写 `generate_signals(context) -> list[Signal]`；
4. 返回 `Signal` 列表，`score` 越大的股票越优先入选。

### 参数自省（不囿于固定参数）

平台用 `inspect.signature(cls.__init__)` 读取构造函数签名，自动生成网页参数表单：

- 每个带默认值的关键字参数都是一个可调参数，个数与类型完全由你决定；
- 默认值类型决定控件类型：`bool` → 开关，`int` → 整数，`float` → 小数，`str` → 文本框；
- `param_specs`（可选）用于覆盖标签、取值范围、可选值与说明；
- 保留名 `strategy_id` 由平台自动注入，无需在 `__init__` 中声明（也可声明以在构造期使用）；
- 平台不再要求实现 `from_parameters` 或声明 `StrategyParameter` 列表。

`param_specs` 支持的关键字：`label`、`min`、`max`、`choices`、`kind`（`integer/number/boolean/string`）、
`description`。

### 注册机制

`register_strategy(name, *, display_name=None, description=None)` 采用与 OpenMMLab
`register_module` 相同的装饰器模式：被装饰的类按 `name` 存入运行时注册表，`name` 即策略的唯一
插件标识。标识只能包含字母、数字和下划线，且以字母开头；不能与内置策略或其它自定义策略重名。

## 数据访问约定

策略只能通过 `StrategyContext` 读取**截至当前信号日**的数据，避免未来函数：

- `context.trade_date`：当前信号日；
- `context.universe`：当前股票池；
- `context.history(fields, lookback=None)`：点及时的行情切片（防御性拷贝）；
- `context.require_fields(...)`：运行前校验字段是否存在；
- `context.portfolio_drawdown`：组合当前回撤（可做风控开关）。

常用行情字段：`adjusted_close`（前复权收盘）、`raw_open/raw_high/raw_low/raw_close`（未复权）、
`amount`（成交额）、`volume`（成交量）、`up_limit/down_limit`（涨跌停）、`is_suspended`、
`is_st`、`quality_status`。

策略只输出信号，不直接下单或改账户；组合、风控、订单、成交由平台负责。

## 存储

已保存的自定义策略位于 `runtime/user_strategies/<标识>/`：

```text
strategy.py       用户策略源码
metadata.json     显示名、说明、来源、创建与更新时间
```

平台启动时会自动发现并加载这些策略，失败项不会中断其它页面，只在页面顶部折叠展示。

## 安全边界

- 高级模式会在本地进程中运行你提供的 Python 代码，导入受白名单限制
  （放行 pandas/numpy/math/quant_platform 等，拦截 os/sys/subprocess/socket/importlib 等）；
- 该白名单是**防误操作**措施，并非安全隔离：纯 Python 进程内执行无法做到硬隔离；
- 请只运行你信任的策略代码；本平台用于研究与模拟，不连接真实券商、不构成投资建议。
