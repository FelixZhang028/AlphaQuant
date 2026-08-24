"""腾讯/同花顺公共工具：实时报价与代码归一化（供 CN 数据源复用）。

- ``tencent_quote``：腾讯 ``qt.gtimg.cn`` 实时报价（名称/最新价/昨收/市值），
  直连接口，不依赖东财。
- ``ths_symbol``：归一化为同花顺行情代码（``002466`` → ``hs_002466``）。
"""

from __future__ import annotations

import re

import requests

from trading_agents.utils import get_logger

log = get_logger(__name__)

_CN_CODE_RE = re.compile(r"(\d{6})")
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_TENCENT_HEADERS = {
    "Referer": "https://gu.qq.com",
    "User-Agent": _UA,
}


def extract_cn_code(symbol: str) -> str | None:
    """从任意代码表示中提取 6 位 A 股数字代码。"""
    m = _CN_CODE_RE.search(symbol)
    return m.group(1) if m else None


def is_shanghai(code: str) -> bool:
    return code.startswith(("6", "9"))


def ths_symbol(symbol: str) -> str:
    """归一化为同花顺行情代码：``002466.SZ``/``sz002466`` → ``hs_002466``。"""
    code = extract_cn_code(symbol)
    if not code:
        raise ValueError(f"无法识别 A 股代码: {symbol!r}")
    return f"{'sh' if is_shanghai(code) else 'hs'}_{code}"


def tencent_quote(symbol: str) -> dict | None:
    """腾讯实时报价；失败返回 None（不抛错）。

    返回字段：name / last / prev_close / open / high / low /
    volume(手) / pct_change / total_market_cap(元) / float_market_cap(元)。
    """
    code = extract_cn_code(symbol)
    if not code:
        return None
    tx_code = f"{'sh' if is_shanghai(code) else 'sz'}{code}"
    try:
        r = requests.get(
            f"https://qt.gtimg.cn/q={tx_code}",
            headers=_TENCENT_HEADERS, timeout=8,
        )
        parts = r.text.split("~")
        if len(parts) < 50:
            return None
        return {
            "name": parts[1],
            "last": float(parts[3]),
            "prev_close": float(parts[4]),
            "open": float(parts[5]),
            "volume": float(parts[6]),  # 手
            "pct_change": float(parts[32]) / 100.0,
            "total_market_cap": float(parts[44]) * 1e8,  # 亿 → 元
            "float_market_cap": float(parts[45]) * 1e8,
        }
    except Exception as exc:  # noqa: BLE001 - 报价失败不阻塞
        log.debug("腾讯报价失败 %s: %s", symbol, exc)
        return None
