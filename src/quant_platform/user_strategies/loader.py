"""Load user strategy source files into registered strategy classes.

User source is executed inside a restricted namespace whose ``__builtins__``
expose a ``__import__`` allowlist. This is a best-effort guard against
accidental misuse, not a security boundary: the platform is a single-user local
research tool and advanced mode executes trusted user code in-process.
"""

from __future__ import annotations

import builtins
import inspect
import sys
from dataclasses import dataclass
from typing import Any

from quant_platform.core.exceptions import ConfigurationError, PluginError
from quant_platform.strategies.base import Strategy
from quant_platform.user_strategies.base import (
    _clear_user_registry,
    _registered_user_strategies,
)

_ALLOWED_TOP_LEVEL = {
    "abc",
    "collections",
    "dataclasses",
    "datetime",
    "decimal",
    "enum",
    "functools",
    "itertools",
    "math",
    "numpy",
    "operator",
    "pandas",
    "quant_platform",
    "re",
    "statistics",
    "typing",
}

_FORBIDDEN_TOP_LEVEL = {
    "atexit",
    "builtins",
    "ctypes",
    "gc",
    "http",
    "importlib",
    "inspect",
    "marshal",
    "multiprocessing",
    "os",
    "pathlib",
    "pickle",
    "requests",
    "shutil",
    "signal",
    "socket",
    "subprocess",
    "sys",
    "threading",
    "urllib",
}

_REAL_IMPORT = builtins.__import__


def _safe_import(
    name: str,
    globals: Any = None,
    locals: Any = None,
    fromlist: tuple[str, ...] = (),
    level: int = 0,
) -> Any:
    root = name.split(".", 1)[0]
    if root in _FORBIDDEN_TOP_LEVEL:
        raise ImportError(f"策略代码禁止导入模块：{name}")
    if root in _ALLOWED_TOP_LEVEL or name in sys.modules:
        return _REAL_IMPORT(name, globals, locals, fromlist, level)
    raise ImportError(f"策略代码禁止导入模块：{name}")


def _forbidden(name: str) -> Any:
    def _blocked(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(f"策略代码禁止使用：{name}")

    return _blocked


def _build_namespace() -> dict[str, Any]:
    safe_builtins = dict(vars(builtins))
    safe_builtins["__import__"] = _safe_import
    for name in ("open", "exec", "eval", "compile", "input", "breakpoint", "__loader__"):
        safe_builtins[name] = _forbidden(name)
    return {"__name__": "alphaquant_user_strategy", "__builtins__": safe_builtins}


@dataclass(frozen=True)
class UserStrategyLoadResult:
    """Outcome of loading one source file: valid classes and per-item errors."""

    strategies: dict[str, type[Strategy]]
    errors: tuple[tuple[str, str], ...]


class UserStrategyLoader:
    """Execute user source in a restricted namespace and collect registrations."""

    def load_source(self, source: str, *, label: str = "strategy") -> UserStrategyLoadResult:
        """Compile and execute one source string, returning registered classes."""

        _clear_user_registry()
        try:
            code = compile(source, f"<user_strategy:{label}>", "exec")
            exec(code, _build_namespace())
        except Exception as exc:
            _clear_user_registry()
            return UserStrategyLoadResult({}, ((label, f"{type(exc).__name__}: {exc}"),))
        registered = _registered_user_strategies()
        strategies: dict[str, type[Strategy]] = {}
        errors: list[tuple[str, str]] = []
        for name, cls in registered.items():
            try:
                self._validate(name, cls)
                strategies[name] = cls
            except (PluginError, ConfigurationError, ValueError) as exc:
                errors.append((name, str(exc)))
        _clear_user_registry()
        return UserStrategyLoadResult(strategies, tuple(errors))

    @staticmethod
    def _validate(name: str, cls: type[Strategy]) -> None:
        if inspect.isabstract(cls):
            raise PluginError("策略类仍是抽象类：必须实现 generate_signals")
        if not callable(getattr(cls, "generate_signals", None)):
            raise PluginError("策略类缺少 generate_signals 方法")
        # Surface parameter-schema problems (missing defaults, bad types) early.
        cls.metadata()
