"""股票代码规范化：FellowQuant 存 6 位裸码，quant_platform 数据层带交易所后缀。"""

from __future__ import annotations

import re

from quant_platform.application.benchmarks import BENCHMARK_NAMES
from quant_platform.data.normalizers import canonical_symbol

_BARE_RE = re.compile(r"^\d{6}$")


def to_canonical(code: str) -> str:
    """把 6 位裸码或任意输入规范成 ``600519.SH`` 形式。"""

    text = str(code).strip()
    if not text:
        return text
    return canonical_symbol(text)


def to_bare(symbol: str) -> str:
    """把 ``600519.SH`` 形式规范成 6 位裸码。"""

    text = str(symbol).strip()
    if "." in text:
        text = text.split(".", 1)[0]
    return text


def is_bare_code(code: str) -> bool:
    return bool(_BARE_RE.fullmatch(str(code).strip()))


def index_symbol(code: str) -> str | None:
    """带后缀的常用指数代码（``000001.SH`` 上证指数）原样返回，否则返回 None。

    指数和股票可能同号（000001 是平安银行），所以只认带后缀的完整代码；
    ``to_canonical`` 按股票规则推断交易所，会把 ``000001.SH`` 改成 ``000001.SZ``，不能用来判断。
    """

    text = str(code).strip().upper()
    return text if text in BENCHMARK_NAMES else None
