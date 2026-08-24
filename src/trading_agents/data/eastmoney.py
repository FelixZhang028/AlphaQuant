"""EastMoneyProvider：东方财富公开接口的 A 股数据源（akshare 同源）。

选择直接调东财接口而非 akshare 库的原因：本机环境下东财的 HTTPS 会对
Python OpenSSL 栈的 TLS 指纹直接 RST 断连（curl/浏览器正常），而 HTTP
端点稳定可用；akshare 内部走 requests+HTTPS 无法注入会话，故自行实现。

特性：
- requests 会话 ``trust_env=False``：A 股为国内站点，强制直连，避免
  系统代理（VPN）把国内流量绕行境外导致失败。
- 名称/行业/总市值来自东财实时报价接口，保证身份接地（防 LLM 幻觉市值）。
- 行情写 SQLite 缓存；网络失败时缓存兜底，无缓存则明确抛错。
- 代码归一化：``002466`` / ``002466.SZ`` / ``sz002466`` → secid ``0.002466``；
  6 开头（沪）→ ``1.600519``。
"""

from __future__ import annotations

import datetime as dt
import json
import re
import time
from pathlib import Path

import requests

from trading_agents.data.base import DataProvider
from trading_agents.data.cache import BarCache
from trading_agents.schemas import MarketSnapshot, OHLCVBar, Ticker
from trading_agents.schemas.models import Market
from trading_agents.utils import get_logger

log = get_logger(__name__)

_QUOTE_PATHS = [
    "push2.eastmoney.com/api/qt/stock/get",
    "push2delay.eastmoney.com/api/qt/stock/get",  # 延时镜像，主站被断时的回退
]
_KLINE_PATHS = ["push2his.eastmoney.com/api/qt/stock/kline/get"]
_SINA_KLINE_URL = (
    "quotes.sina.cn/cn/api/jsonp_v2.php/x/"
    "CN_MarketDataService.getKLineData"
)
_UT = "7eea3edcaed734bea9cbfc24409ed989"
_QUOTE_FIELDS = "f57,f58,f43,f44,f45,f46,f47,f48,f60,f116,f117,f127,f128,f170"

# 新浪对无浏览器 UA 的请求会返回反盗链脚本（仅 location.href 重定向，无数据）。
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_SINA_HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": _UA,
    "Accept": "*/*",
}

_CN_CODE_RE = re.compile(r"(\d{6})")


def extract_jsonp_array(text: str) -> list | None:
    """从 JSONP 响应中提取数组；容忍 ``/*...*/`` 注释前缀与重定向脚本。

    新浪新版响应形如 ``/*<script>location.href=\\'//sina.com\\';</script>*/\nx([...])``，
    反盗链时则只返回注释脚本（无括号、无数据）。去掉注释块后再定位括号。
    """
    cleaned = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    lpar = cleaned.find("(")
    rpar = cleaned.rfind(")")
    if lpar < 0 or rpar <= lpar:
        return None
    try:
        return json.loads(cleaned[lpar + 1:rpar])
    except json.JSONDecodeError:
        return None


def normalize_secid(symbol: str) -> str:
    """归一化 A 股代码为东财 secid（``0.``=深/创，``1.``=沪/科）。"""
    m = _CN_CODE_RE.search(symbol)
    if not m:
        raise ValueError(f"无法识别 A 股代码: {symbol!r}")
    code = m.group(1)
    market = "1" if code.startswith(("6", "9")) else "0"
    return f"{market}.{code}"


def normalize_symbol(symbol: str) -> str:
    """归一化为带后缀的标准形式，如 ``002466.SZ`` / ``688981.SS``。"""
    secid = normalize_secid(symbol)
    market, code = secid.split(".")
    return f"{code}.{'SS' if market == '1' else 'SZ'}"


def sina_symbol(symbol: str) -> str:
    """归一化为新浪代码，如 ``sz002466`` / ``sh688981``。"""
    secid = normalize_secid(symbol)
    market, code = secid.split(".")
    return f"{'sh' if market == '1' else 'sz'}{code}"


class _Transport:
    """多通道 HTTP 传输：VPN 路由切换时各数据接口的可达路径会变化，按序回退。

    对每个候选 ``host/path`` 依次尝试：
    1. HTTP 直连（国内站点常规路径，trust_env=False 绕开系统代理）
    2. HTTPS 直连
    3. HTTPS 走系统代理（VPN 全局接管时可能唯一可达）
    首个成功组合缓存复用；``ok`` 回调校验响应内容（如 K 线为空视为失败，
    继续尝试下一通道），全部失败后整体重试一次（东财间歇性 RST 常见）。
    """

    def __init__(self, timeout: int = 10, retries: int = 1) -> None:
        self._timeout = timeout
        self._retries = retries
        self._direct = requests.Session()
        self._direct.trust_env = False  # 直连：不读系统代理
        self._proxied = requests.Session()  # 默认读系统代理
        self._channels: list[tuple[str, requests.Session]] = [
            ("http", self._direct),
            ("https", self._direct),
            ("https", self._proxied),
        ]
        self._working: tuple[str, str, requests.Session] | None = None

    def get_json(
        self,
        paths: list[str] | str,
        params: dict,
        headers: dict | None = None,
        ok=None,
    ) -> requests.Response:
        if isinstance(paths, str):
            paths = [paths]
        combos: list[tuple[str, str, requests.Session]] = []
        # 缓存的可用通道只在请求同一 API 路径时复用；跨接口（如新浪）复用
        # 会把上一接口的参数打到错误主机上，必须排除。
        if self._working and self._working[0] in paths:
            combos.append(self._working)
        for path in paths:
            for scheme, session in self._channels:
                cand = (path, scheme, session)
                if cand != self._working:
                    combos.append(cand)
        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            for path, scheme, session in combos:
                try:
                    r = session.get(
                        f"{scheme}://{path}", params=params,
                        headers=headers or {}, timeout=self._timeout,
                    )
                    r.raise_for_status()
                    if ok is not None and not ok(r):
                        raise RuntimeError(f"{scheme}://{path} 内容不可用")
                    self._working = (path, scheme, session)
                    return r
                except Exception as exc:  # noqa: BLE001 - 逐通道回退
                    last_exc = exc
                    log.debug("数据通道 %s://%s 失败: %s", scheme, path, exc)
            if attempt < self._retries:
                log.warning("数据接口所有通道失败，%s 秒后整体重试（第 %d 次）",
                            (attempt + 1), attempt + 1)
                time.sleep(0.8 * (attempt + 1))
        raise RuntimeError(f"数据接口所有通道均不可用: {last_exc}")


class EastMoneyProvider(DataProvider):
    """东方财富 A 股数据源。"""

    name = "eastmoney"

    def __init__(self, cache: BarCache | None = None, cache_path: Path | None = None) -> None:
        self._transport = _Transport()
        if cache is None and cache_path is not None:
            cache = BarCache(cache_path)
        self.cache = cache

    # ------------------------------------------------------------ 接口 ----
    def resolve(self, symbol: str, market: str) -> Ticker:
        secid = normalize_secid(symbol)
        q = self._quote(secid)
        return Ticker(
            symbol=normalize_symbol(symbol),
            market=Market.CN,
            name=str(q.get("f58") or symbol),
            industry=str(q.get("f127") or ""),
            currency="CNY",
        )

    def get_snapshot(
        self, ticker: Ticker, as_of_date: dt.date, lookback_days: int = 60
    ) -> MarketSnapshot:
        start = as_of_date - dt.timedelta(days=int(lookback_days * 1.6) + 10)
        bars: list[OHLCVBar] = []
        if self.cache and self.cache.covers(ticker.symbol, start, as_of_date):
            bars = self.cache.get(ticker.symbol, start, as_of_date)
        if not bars:
            try:
                bars = self._download_bars(ticker.symbol, start, as_of_date)
                if self.cache:
                    self.cache.put(ticker.symbol, bars)
            except Exception as exc:  # noqa: BLE001 - 网络失败降级缓存
                log.warning("东财行情下载失败，尝试缓存降级: %s", exc)
                if self.cache:
                    bars = self.cache.get(ticker.symbol, start, as_of_date)
                if not bars:
                    raise RuntimeError(
                        f"无法获取 {ticker.symbol} 行情：网络失败且无可用缓存"
                    ) from exc
        bars = [b for b in bars if b.date <= as_of_date]  # 快照语义
        if not bars:
            raise RuntimeError(f"no bars on or before {as_of_date} for {ticker.symbol}")
        quote: dict = {}
        try:
            quote = self._quote(normalize_secid(ticker.symbol))
        except Exception as exc:  # noqa: BLE001 - 报价失败不阻塞，仅记日志
            log.warning("东财实时报价拉取失败（降级为空）: %s", exc)
        prev_close = bars[-2].close if len(bars) > 1 else bars[-1].close
        fundamentals: dict[str, float | str] = {"prev_close": prev_close}
        market_cap = None
        if quote:
            if quote.get("f116"):
                market_cap = float(quote["f116"])
                fundamentals["total_market_cap_cny"] = market_cap
            if quote.get("f117"):
                fundamentals["float_market_cap_cny"] = float(quote["f117"])
            if quote.get("f170") is not None:
                fundamentals["pct_change_latest"] = float(quote["f170"]) / 100.0
        return MarketSnapshot(
            ticker=ticker,
            as_of_date=as_of_date,
            bars=bars,
            last_close=bars[-1].close,
            market_cap=market_cap,
            index="CSI300",
            fundamentals=fundamentals,
            news=[],  # 东财新闻接口未接入，情绪/新闻分析师将明确标注无新闻输入
        )

    def get_bars_after(self, ticker: Ticker, start: dt.date, days: int) -> list[OHLCVBar]:
        end = start + dt.timedelta(days=days * 2 + 10)
        bars: list[OHLCVBar] = []
        if self.cache:
            bars = self.cache.get(ticker.symbol, start, end)
        if not bars:
            bars = self._download_bars(ticker.symbol, start, end)
            if self.cache:
                self.cache.put(ticker.symbol, bars)
        return [b for b in bars if b.date > start][:days]

    # ------------------------------------------------------------ 内部 ----
    def _quote(self, secid: str) -> dict:
        def _ok(r: requests.Response) -> bool:
            try:
                return bool(r.json().get("data"))
            except Exception:  # noqa: BLE001 - 内容不可用视为通道失败
                return False

        r = self._transport.get_json(
            _QUOTE_PATHS, dict(secid=secid, fltt=2, invt=2, fields=_QUOTE_FIELDS),
            ok=_ok,
        )
        data = r.json().get("data")
        if not data:
            raise RuntimeError(f"东财报价接口无数据: {secid}")
        return data

    def _download_bars(self, symbol: str, start: dt.date, end: dt.date) -> list[OHLCVBar]:
        try:
            return self._download_bars_em(symbol, start, end)
        except Exception as exc:  # noqa: BLE001 - 东财 K 线不可达时回退新浪
            log.warning("东财 K 线失败，回退新浪日线: %s", exc)
            return self._download_bars_sina(symbol, start, end)

    def _download_bars_em(self, symbol: str, start: dt.date, end: dt.date) -> list[OHLCVBar]:
        def _ok(r: requests.Response) -> bool:
            try:
                data = r.json().get("data") or {}
                return bool(data.get("klines"))
            except Exception:  # noqa: BLE001 - 内容不可用视为通道失败
                return False

        r = self._transport.get_json(
            _KLINE_PATHS,
            dict(
                secid=normalize_secid(symbol), klt=101, fqt=1,
                fields1="f1,f2,f3,f4,f5,f6",
                fields2="f51,f52,f53,f54,f55,f56",
                beg=start.strftime("%Y%m%d"), end=end.strftime("%Y%m%d"), ut=_UT,
            ),
            ok=_ok,
        )
        data = r.json().get("data")
        if not data or not data.get("klines"):
            raise RuntimeError(f"eastmoney returned no data for {symbol} in [{start}, {end}]")
        bars: list[OHLCVBar] = []
        for line in data["klines"]:
            # f51 日期, f52 开, f53 收, f54 高, f55 低, f56 成交量(手)
            d, o, c, hi, lo, vol = line.split(",")[:6]
            bars.append(
                OHLCVBar(
                    date=dt.date.fromisoformat(d), open=float(o), close=float(c),
                    high=float(hi), low=float(lo), volume=int(float(vol)) * 100,
                )
            )
        return bars

    def _download_bars_sina(self, symbol: str, start: dt.date, end: dt.date) -> list[OHLCVBar]:
        """新浪日线（不复权）作为东财 K 线的兜底。

        注意：新浪 ``datalen`` 返回的是**截止今天**最近 N 根，而非截止
        ``end``；因此按 ``今天 - start`` 推算所需根数（上限 1023），
        再按 [start, end] 过滤。历史回测日期（如 2025-06-03）因此可用。
        """
        days_needed = int((dt.date.today() - start).days * 1.5) + 10
        r = self._transport.get_json(
            _SINA_KLINE_URL,
            dict(symbol=sina_symbol(symbol), scale=240, ma="no", datalen=min(days_needed, 1023)),
            headers=_SINA_HEADERS,
        )
        data = extract_jsonp_array(r.text)
        if not data:
            raise RuntimeError(f"sina kline: unexpected payload for {symbol}")
        bars: list[OHLCVBar] = []
        for item in data:
            day = dt.date.fromisoformat(item["day"])
            if start <= day <= end:
                bars.append(
                    OHLCVBar(
                        date=day, open=float(item["open"]), close=float(item["close"]),
                        high=float(item["high"]), low=float(item["low"]),
                        volume=int(float(item["volume"])),
                    )
                )
        if not bars:
            raise RuntimeError(f"sina returned no bars in [{start}, {end}] for {symbol}")
        return bars
