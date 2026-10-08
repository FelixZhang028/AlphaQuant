"""Static safety checks for user-supplied strategy source code.

The loader executes user code inside a best-effort restricted namespace; this
module adds an AST-based review layer that runs *before* saving, producing a
structured report of blockers (must fix) and warnings (must acknowledge). It is
heuristic by design and complements, not replaces, the runtime guards.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from quant_platform.user_strategies.loader import (
    _ALLOWED_TOP_LEVEL,
    _FORBIDDEN_TOP_LEVEL,
)

#: Builtins that user strategy code must never call.
FORBIDDEN_CALLS: frozenset[str] = frozenset(
    {"open", "exec", "eval", "compile", "input", "__import__", "breakpoint"}
)

#: Fields actually available on ``daily_bars`` / ``StrategyContext.history``.
#: Mirrors ``quant_platform.data.models.DailyBar`` plus common OHLC aliases.
KNOWN_FIELDS: frozenset[str] = frozenset(
    {
        "symbol",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "raw_open",
        "raw_high",
        "raw_low",
        "raw_close",
        "pre_close",
        "adjusted_close",
        "volume",
        "amount",
        "adj_factor",
        "up_limit",
        "down_limit",
        "is_suspended",
        "is_st",
    }
)

_BLOCKER = "blocker"
_WARNING = "warning"


@dataclass(frozen=True)
class SafetyIssue:
    """One finding from the static safety review."""

    code: str
    severity: str
    message: str
    line: int | None = None


@dataclass(frozen=True)
class SafetyReport:
    """Aggregated result of :func:`check_strategy_source`."""

    blockers: tuple[SafetyIssue, ...] = ()
    warnings: tuple[SafetyIssue, ...] = ()

    @property
    def blocked(self) -> bool:
        """True when at least one blocker must be fixed before saving."""

        return bool(self.blockers)


@dataclass
class _IssueCollector:
    blockers: list[SafetyIssue] = field(default_factory=list)
    warnings: list[SafetyIssue] = field(default_factory=list)

    def blocker(self, code: str, message: str, line: int | None = None) -> None:
        self.blockers.append(SafetyIssue(code, _BLOCKER, message, line))

    def warning(self, code: str, message: str, line: int | None = None) -> None:
        self.warnings.append(SafetyIssue(code, _WARNING, message, line))


def check_strategy_source(source: str) -> SafetyReport:
    """Run all static checks on user strategy ``source`` and return a report."""

    collector = _IssueCollector()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        collector.blocker("syntax_error", f"代码存在语法错误：{exc.msg}", exc.lineno)
        return SafetyReport(tuple(collector.blockers), tuple(collector.warnings))

    _check_imports(tree, collector)
    _check_forbidden_calls(tree, collector)
    _check_future_leakage(tree, collector)
    _check_init_params(tree, collector)
    _check_required_fields(tree, collector)
    _check_cn_rules_hint(tree, collector)
    return SafetyReport(tuple(collector.blockers), tuple(collector.warnings))


def _check_imports(tree: ast.AST, collector: _IssueCollector) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _check_module(alias.name, node.lineno, collector)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                collector.blocker(
                    "relative_import", "禁止使用相对导入（from . import ...）", node.lineno
                )
            elif node.module:
                _check_module(node.module, node.lineno, collector)


def _check_module(module: str, line: int, collector: _IssueCollector) -> None:
    root = module.split(".", 1)[0]
    if root in _FORBIDDEN_TOP_LEVEL:
        collector.blocker(
            "forbidden_import",
            f"禁止导入模块 {module!r}（与运行时黑名单一致）",
            line,
        )
    elif root not in _ALLOWED_TOP_LEVEL:
        collector.warning(
            "unlisted_import",
            f"模块 {module!r} 不在允许列表中，运行时会被拒绝导入",
            line,
        )


def _check_forbidden_calls(tree: ast.AST, collector: _IssueCollector) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _called_name(node.func)
        if name in FORBIDDEN_CALLS:
            collector.blocker(
                "forbidden_call", f"禁止调用 {name}()", node.lineno
            )


def _called_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _check_future_leakage(tree: ast.AST, collector: _IssueCollector) -> None:
    for node in ast.walk(tree):
        # .shift(-N) / .shift(periods=-N) reads future rows.
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "shift":
                value = _shift_argument(node)
                if value is not None and value < 0:
                    collector.blocker(
                        "future_shift",
                        f".shift({value}) 会引入未来数据（未来函数），"
                        "信号只能使用截至当日的数据",
                        node.lineno,
                    )
        # ``x[::-1]`` on time series usually precedes look-ahead indexing.
        if isinstance(node, ast.Subscript) and _is_reversed_slice(node.slice):
            collector.warning(
                "reversed_slice",
                "[::-1] 反转时序后取值容易误用未来数据，请确认索引方向",
                node.lineno,
            )
        # Names mentioning "future" are a red flag for look-ahead intent.
        if isinstance(node, (ast.Name, ast.Attribute)):
            name = node.id if isinstance(node, ast.Name) else node.attr
            if "future" in name.lower():
                collector.warning(
                    "future_naming",
                    f"标识符 {name!r} 含 future 字样，请确认没有引用未来数据",
                    node.lineno,
                )
        # Reading data files outside generate_signals (module/class scope).
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "generate_signals":
                continue
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and _looks_like_file_read(call):
                    collector.warning(
                        "global_file_read",
                        "在 generate_signals 之外读取数据文件，可能引入全样本信息",
                        call.lineno,
                    )


def _shift_argument(node: ast.Call) -> int | None:
    candidate: ast.expr | None = node.args[0] if node.args else None
    for keyword in node.keywords:
        if keyword.arg == "periods":
            candidate = keyword.value
    if candidate is None:
        return None
    if isinstance(candidate, ast.UnaryOp) and isinstance(candidate.op, ast.USub):
        if isinstance(candidate.operand, ast.Constant) and isinstance(
            candidate.operand.value, int
        ):
            return -candidate.operand.value
    if isinstance(candidate, ast.Constant) and isinstance(candidate.value, int):
        return candidate.value
    return None


def _is_reversed_slice(slice_node: ast.expr) -> bool:
    if not isinstance(slice_node, ast.Slice):
        return False
    step = slice_node.step
    return (
        isinstance(step, ast.UnaryOp)
        and isinstance(step.op, ast.USub)
        and isinstance(step.operand, ast.Constant)
        and step.operand.value == 1
    )


def _looks_like_file_read(node: ast.Call) -> bool:
    name = _called_name(node.func)
    if name in {"read_csv", "read_parquet", "read_excel", "read_pickle", "loadtxt"}:
        return True
    return False


def _check_init_params(tree: ast.AST, collector: _IssueCollector) -> None:
    allowed = (int, float, str, bool)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        init = next(
            (
                item
                for item in node.body
                if isinstance(item, ast.FunctionDef) and item.name == "__init__"
            ),
            None,
        )
        if init is None:
            continue
        args = init.args.args[1:]  # skip self
        defaults = [None] * (len(args) - len(init.args.defaults)) + list(init.args.defaults)
        for arg, default in zip(args, defaults, strict=True):
            if arg.arg == "strategy_id":
                continue
            if default is None:
                collector.blocker(
                    "param_missing_default",
                    f"类 {node.name}.__init__ 的参数 {arg.arg!r} 缺少默认值，"
                    "平台无法为其生成参数表单",
                    arg.lineno,
                )
                continue
            if not (isinstance(default, ast.Constant) and isinstance(default.value, allowed)):
                collector.warning(
                    "param_default_complex",
                    f"类 {node.name}.__init__ 的参数 {arg.arg!r} 默认值不是"
                    " int/float/str/bool 字面量，网页表单可能无法正确展示",
                    default.lineno,
                )


def _check_required_fields(tree: ast.AST, collector: _IssueCollector) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not isinstance(item, ast.Assign):
                continue
            if not any(
                isinstance(target, ast.Name) and target.id == "required_fields"
                for target in item.targets
            ):
                continue
            fields = _literal_string_set(item.value)
            if fields is None:
                collector.warning(
                    "required_fields_dynamic",
                    f"类 {node.name} 的 required_fields 不是字面量集合，无法静态校验",
                    item.lineno,
                )
                continue
            if not fields:
                collector.blocker(
                    "required_fields_empty",
                    f"类 {node.name} 的 required_fields 不能为空集合",
                    item.lineno,
                )
                continue
            unknown = sorted(fields - KNOWN_FIELDS)
            if unknown:
                collector.blocker(
                    "required_fields_unknown",
                    f"类 {node.name} 的 required_fields 含未知字段："
                    f"{', '.join(unknown)}；可用字段见 daily_bars 列定义",
                    item.lineno,
                )


def _literal_string_set(node: ast.expr) -> set[str] | None:
    """Extract a set of string constants from ``{...}`` / ``frozenset({...})``."""

    target = node
    if isinstance(node, ast.Call) and _called_name(node.func) == "frozenset" and node.args:
        target = node.args[0]
    if not isinstance(target, (ast.Set, ast.List, ast.Tuple)):
        return None
    values: set[str] = set()
    for element in target.elts:
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            values.add(element.value)
        else:
            return None
    return values


def _check_cn_rules_hint(tree: ast.AST, collector: _IssueCollector) -> None:
    tokens: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            tokens.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            tokens.add(node.attr.lower())
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            tokens.update(part.lower() for part in node.value.replace("_", " ").split())
    if not any("limit" in token or "suspend" in token for token in tokens):
        collector.warning(
            "cn_rules_hint",
            "未检测到对涨跌停（up_limit/down_limit）或停牌（is_suspended）的处理；"
            "A 股中这些情形可能导致信号无法成交，建议策略显式过滤",
            None,
        )
