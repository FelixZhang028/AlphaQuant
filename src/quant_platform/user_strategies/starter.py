"""A beginner-friendly starter template shown in the code editor."""

STARTER_STRATEGY_CODE = '''"""我的自定义策略（示例：双均线 + 动量排序）。

使用说明：
1. 继承 BaseStrategy，并用 @register_strategy("唯一英文标识") 注册；
2. 在 __init__ 里声明带默认值的参数，平台会自动生成网页参数表单；
3. 重写 generate_signals，通过 context.history() 只读取截至当天的数据；
4. 返回 Signal 列表，score 越大的股票越优先入选。

常用行情字段（可在 required_fields 之外通过 context.history 使用）：
adjusted_close（前复权收盘）、raw_close/raw_high/raw_low（未复权）、amount（成交额）、
volume（成交量）、up_limit/down_limit（涨跌停）、is_suspended、is_st 等。
"""

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
    # 策略需要哪些行情字段（平台会在运行前校验数据是否满足）
    required_fields = frozenset({"symbol", "trade_date", "adjusted_close", "amount"})

    # 可选：给参数更友好的网页标签、取值范围和说明
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
'''
