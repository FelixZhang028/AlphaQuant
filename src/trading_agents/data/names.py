"""股票代码 → 名称的解析与兜底。

数据源（stub / yfinance）在离线或网络限流时可能只返回占位名或直接把
代码当作名称；本模块内置一份常见 A 股代码→名称映射表，在数据源名称
"不可用"时兜底替换，确保分析/辩论阶段能拿到可读的标的名称。

优先级：数据源真实名称 > 内置映射表 > 原样返回。
"""

from __future__ import annotations

import re

# 常见 A 股代码 → 名称（key 统一为 6 位数字代码，不带市场后缀）。
# 仅在数据源名称不可用（占位符 / 缺失 / 回退为代码本身）时兜底使用。
CN_NAME_OVERRIDES: dict[str, str] = {
    # --- 科创板 ---
    "688836": "东威科技",
    "688981": "中芯国际",
    "688041": "海光信息",
    "688111": "金山办公",
    "688256": "寒武纪",
    "688036": "传音控股",
    # --- 主板（沪）---
    "600519": "贵州茅台",
    "601318": "中国平安",
    "600036": "招商银行",
    "600030": "中信证券",
    "601988": "中国银行",
    "600276": "恒瑞医药",
    "601899": "紫金矿业",
    # --- 主板（深）---
    "000001": "平安银行",
    "000858": "五粮液",
    "002594": "比亚迪",
    # --- 创业板 ---
    "300750": "宁德时代",
    "300059": "东方财富",
}

_CN_CODE_RE = re.compile(r"\d{6}")


def extract_cn_code(symbol: str) -> str | None:
    """从任意代码表示中提取 6 位 A 股数字代码。

    支持 ``688836.SS`` / ``688836`` / ``SH688836`` / ``688836.sz`` 等形式。
    """
    m = _CN_CODE_RE.search(symbol)
    return m.group(0) if m else None


def _name_usable(name: str, symbol: str) -> bool:
    """判断数据源返回的名称是否"可用"。

    不可用判定：空、与代码本身等价（含大小写与后缀差异，如 yfinance
    网络失败降级为 symbol）、以及 stub 的占位名（``XXX (stub)``）。
    """
    stripped = name.strip()
    if not stripped:
        return False
    if "(stub)" in stripped.lower():
        return False
    norm_name = re.sub(r"[^0-9A-Za-z]", "", stripped).upper()
    norm_symbol = re.sub(r"[^0-9A-Za-z]", "", symbol).upper()
    if norm_name == norm_symbol:
        return False
    return True


def apply_name_fallback(symbol: str, name: str) -> str:
    """对数据源解析出的名称做兜底：不可用时查内置映射表替换。

    Args:
        symbol: 用户输入的标的代码（如 ``688836.SS``）。
        name: 数据源 resolve 返回的名称。

    Returns:
        优先级：真实名称 > 内置映射表 > 原样返回。
    """
    if _name_usable(name, symbol):
        return name
    code = extract_cn_code(symbol)
    if code is not None and code in CN_NAME_OVERRIDES:
        return CN_NAME_OVERRIDES[code]
    return name
