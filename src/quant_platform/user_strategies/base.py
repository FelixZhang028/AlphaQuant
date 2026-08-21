"""User-facing strategy base class and registration decorator.

Advanced users subclass :class:`BaseStrategy`, decorate it with
:func:`register_strategy`, and override :meth:`BaseStrategy.generate_signals`.
The platform introspects the ``__init__`` signature to render a generic
parameter form, so strategies are not limited to a fixed parameter schema.
"""

from __future__ import annotations

import inspect
import re
from abc import abstractmethod
from collections.abc import Callable
from typing import Any, ClassVar, TypeVar

from quant_platform.core.exceptions import ConfigurationError, PluginError
from quant_platform.signals.models import Signal
from quant_platform.strategies.base import Strategy
from quant_platform.strategies.context import StrategyContext
from quant_platform.strategies.spec import ParameterKind, StrategyMetadata, StrategyParameter

_USER_REGISTRY: dict[str, type[Strategy]] = {}
_PLUGIN_NAME_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_]*")
_StrategyT = TypeVar("_StrategyT", bound="BaseStrategy")


def _validate_plugin_name(plugin: str) -> str:
    if not _PLUGIN_NAME_RE.fullmatch(plugin):
        raise PluginError(
            f"策略标识 {plugin!r} 不合法：只能包含字母、数字和下划线，且以字母开头"
        )
    return plugin


def register_strategy(
    name: str,
    *,
    display_name: str | None = None,
    description: str | None = None,
) -> Callable[[type[_StrategyT]], type[_StrategyT]]:
    """Register a :class:`BaseStrategy` subclass under a unique plugin name.

    This mirrors the ``register_model`` decorator pattern from OpenMMLab's
    registry: the decorated class is stored under ``name`` and later built by
    the platform using the parameters inferred from its ``__init__`` signature.
    """

    def decorator(cls: type[_StrategyT]) -> type[_StrategyT]:
        plugin = _validate_plugin_name((name or getattr(cls, "__name__", "")).strip())
        if not issubclass(cls, BaseStrategy):
            raise PluginError("@register_strategy 只能用于 BaseStrategy 的子类")
        if plugin in _USER_REGISTRY:
            raise PluginError(f"策略标识已存在：{plugin}")
        cls.plugin_name = plugin
        cls.display_name = display_name or getattr(cls, "display_name", None) or plugin
        cls.description = description if description is not None else inspect.getdoc(cls) or ""
        _USER_REGISTRY[plugin] = cls
        return cls

    return decorator


def _clear_user_registry() -> None:
    _USER_REGISTRY.clear()


def _registered_user_strategies() -> dict[str, type[Strategy]]:
    return dict(_USER_REGISTRY)


def _infer_kind(default: Any) -> ParameterKind:
    if isinstance(default, bool):
        return ParameterKind.BOOLEAN
    if isinstance(default, int):
        return ParameterKind.INTEGER
    if isinstance(default, float):
        return ParameterKind.NUMBER
    if isinstance(default, str):
        return ParameterKind.STRING
    raise ConfigurationError(
        f"策略参数默认值类型不受支持：{default!r}，请使用 int/float/bool/str"
    )


def _kind_from_spec(value: Any) -> ParameterKind | None:
    if value is None:
        return None
    if isinstance(value, ParameterKind):
        return value
    text = str(value).strip().lower()
    return {
        "integer": ParameterKind.INTEGER,
        "int": ParameterKind.INTEGER,
        "number": ParameterKind.NUMBER,
        "float": ParameterKind.NUMBER,
        "boolean": ParameterKind.BOOLEAN,
        "bool": ParameterKind.BOOLEAN,
        "string": ParameterKind.STRING,
        "str": ParameterKind.STRING,
    }.get(text)


def _as_number(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


class BaseStrategy(Strategy):
    """Flexible user strategy base class.

    子类只需：

    1. 用 ``@register_strategy("唯一英文标识")`` 注册；
    2. 在 ``__init__`` 中声明带默认值的自定义参数（平台据此生成网页表单）；
    3. 重写 :meth:`generate_signals`，通过 ``context.history()`` 读取截至当天的数据；
    4. 返回 ``Signal`` 列表，``score`` 越大的股票越优先入选。

    参数不受固定字段限制：任意带默认值的关键字参数都会被平台识别并自动生成表单。
    """

    required_fields: ClassVar[frozenset[str]] = frozenset(
        {"symbol", "trade_date", "adjusted_close"}
    )
    param_specs: ClassVar[dict[str, dict[str, Any]]] = {}

    def __init__(self, **params: Any) -> None:
        self.strategy_id = str(params.pop("strategy_id", ""))
        for name, value in params.items():
            setattr(self, name, value)

    @classmethod
    def metadata(cls) -> StrategyMetadata:
        return StrategyMetadata(
            plugin_name=cls.plugin_name,
            display_name=cls.display_name,
            description=cls.description,
            parameters=cls._introspected_parameters(),
            required_fields=cls.required_fields,
        )

    @classmethod
    def from_parameters(cls, strategy_id: str, parameters: dict[str, Any]) -> BaseStrategy:
        return _instantiate(cls, strategy_id, parameters)

    @classmethod
    def _introspected_parameters(cls) -> tuple[StrategyParameter, ...]:
        signature = inspect.signature(cls.__init__)
        specs = cls.param_specs if isinstance(cls.param_specs, dict) else {}
        parameters: list[StrategyParameter] = []
        for name, parameter in signature.parameters.items():
            if name in {"self", "strategy_id"}:
                continue
            if parameter.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
                inspect.Parameter.POSITIONAL_ONLY,
            ):
                continue
            if parameter.default is inspect.Parameter.empty:
                raise ConfigurationError(
                    f"策略 {cls.plugin_name} 的参数 {name} 需要提供默认值"
                )
            raw_spec = specs.get(name)
            spec = raw_spec if isinstance(raw_spec, dict) else {}
            kind = _kind_from_spec(spec.get("kind")) or _infer_kind(parameter.default)
            parameters.append(
                StrategyParameter(
                    name=name,
                    label=str(spec.get("label", name)),
                    kind=kind,
                    default=parameter.default,
                    description=str(spec.get("description", "")),
                    minimum=_as_number(spec.get("min")),
                    maximum=_as_number(spec.get("max")),
                    choices=tuple(str(item) for item in spec.get("choices", ())),
                )
            )
        return tuple(parameters)

    @abstractmethod
    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        """Return point-in-time signals; ``score`` ranks candidates for selection."""

        raise NotImplementedError


def _instantiate(
    cls: type[BaseStrategy], strategy_id: str, parameters: dict[str, Any]
) -> BaseStrategy:
    """Instantiate a user strategy, injecting ``strategy_id`` regardless of signature."""

    signature = inspect.signature(cls.__init__)
    if "strategy_id" in signature.parameters:
        return cls(strategy_id=strategy_id, **parameters)
    instance = cls(**parameters)
    instance.strategy_id = strategy_id
    return instance
