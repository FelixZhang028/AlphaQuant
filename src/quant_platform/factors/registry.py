"""因子注册表：管理因子定义的注册、查询与枚举。"""

from __future__ import annotations

from quant_platform.factors.base import FactorDefinition
from quant_platform.factors.builtins import builtin_factors
from quant_platform.factors.custom import load_custom_factors


class FactorRegistry:
    """按名称索引的因子注册表。"""

    def __init__(self) -> None:
        self._factors: dict[str, FactorDefinition] = {}

    def register(self, factor: FactorDefinition, *, replace: bool = False) -> None:
        """注册因子；同名且未指定 ``replace`` 时抛出冲突错误。"""

        if not factor.name:
            raise ValueError("因子 name 不能为空")
        if factor.name in self._factors and not replace:
            raise ValueError(f"因子已存在: {factor.name}")
        self._factors[factor.name] = factor

    def get(self, name: str) -> FactorDefinition:
        """按英文名获取因子定义。"""

        try:
            return self._factors[name]
        except KeyError:
            available = "、".join(sorted(self._factors)) or "（空）"
            raise KeyError(f"未找到因子 {name!r}，已注册: {available}") from None

    def list(self, category: str | None = None) -> list[FactorDefinition]:
        """列出全部因子，可按类别过滤，按名称排序。"""

        factors = sorted(self._factors.values(), key=lambda item: item.name)
        if category is not None:
            factors = [item for item in factors if item.category == category]
        return factors

    def __contains__(self, name: str) -> bool:
        return name in self._factors

    def __len__(self) -> int:
        return len(self._factors)


_DEFAULT_REGISTRY: FactorRegistry | None = None


def _build_registry() -> FactorRegistry:
    """构建一个包含内置因子与持久化自定义因子的注册表。"""
    registry = FactorRegistry()
    for factor in builtin_factors():
        registry.register(factor)
    for factor in load_custom_factors():
        try:
            registry.register(factor, replace=True)
        except ValueError:
            # 非法或与内置因子重名的自定义因子直接跳过
            continue
    return registry


def default_registry() -> FactorRegistry:
    """全局默认注册表，自动注册全部内置因子与已持久化的自定义因子。"""

    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = _build_registry()
    return _DEFAULT_REGISTRY


def reload_default_registry() -> FactorRegistry:
    """重新构建默认注册表（在自定义因子增删后调用）。"""

    global _DEFAULT_REGISTRY
    _DEFAULT_REGISTRY = _build_registry()
    return _DEFAULT_REGISTRY
