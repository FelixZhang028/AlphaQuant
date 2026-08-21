"""Public API for advanced custom (Python) strategies.

Import surface users rely on::

    from quant_platform.user_strategies import BaseStrategy, register_strategy
"""

from quant_platform.user_strategies.base import (
    BaseStrategy,
    register_strategy,
)
from quant_platform.user_strategies.loader import (
    UserStrategyLoader,
    UserStrategyLoadResult,
)
from quant_platform.user_strategies.store import (
    UserStrategyRecord,
    UserStrategyStore,
)

__all__ = [
    "BaseStrategy",
    "register_strategy",
    "UserStrategyLoadResult",
    "UserStrategyLoader",
    "UserStrategyRecord",
    "UserStrategyStore",
]
