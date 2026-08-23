"""AkshareProvider：基于 akshare 库的 A 股数据源（源内多端点回退）。

akshare 同一功能常有多数据源实现，本机网络环境下各端点可达性不同：
- ``stock_zh_a_hist_tx``（腾讯）：直连稳定，首选。
- ``stock_zh_a_daily``（新浪）：直连稳定，次选。
- ``stock_zh_a_hist``（东财）：与 eastmoney 源同网段，可能被 RST，末选。

数据源内自动回退 + 外部 ``FallbackProvider`` 跨源回退，形成两级容错。
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from trading_agents.data.base import DataProvider
from trading_agents.data.cache import BarCache
from trading_agents.data.cn_quote import (
    extract_cn_code,
    is_shanghai,
    tencent_quote,
)
from trading_agents.schemas import MarketSnapshot, OHLCVBar, Ticker
from trading_agents.schemas.models import Market
from trading_agents.utils import get_logger

log = get_logger(__name__)


def _no_proxy_akshare():
    """让 akshare 的东财接口走直连（绕开本机 Clash 系统代理）。

    akshare 内部用 requests（trust_env=True），无法注入会话；东财 HTTPS 经
    Clash 代理会被断连（本机已实测），因此调用前临时清空代理环境变量。
    """
    import os
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]
        saved = {k: os.environ.get(k) for k in keys if k in os.environ}
        for k in keys:
            os.environ.pop(k, None)
        os.environ["NO_PROXY"] = "*"
        try:
            yield
        finally:
            for k in keys:
                os.environ.pop(k, None)
            os.environ.update(saved)

    return _ctx()


class AkshareProvider(DataProvider):
    """akshare A 股数据源（源内多端点回退）。"""

    name = "akshare"

    def __init__(self, cache: BarCache | None = None, cache_path: Path | None = None) -> None:
        try:
            import akshare  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "akshare 未安装，无法使用真实行情数据源。"
                "请 `pip install akshare`，或使用 stub 数据源离线运行。"
            ) from exc
        import akshare as ak

        self._ak = ak
        if cache is None and cache_path is not None:
            cache = BarCache(cache_path)
        self.cache = cache

    def resolve(self, symbol: str, market: str) -> Ticker:
        code = extract_cn_code(symbol)
        name = code or symbol
        q = tencent_quote(symbol)
        if q and q.get("name"):
            name = q["name"]
        return Ticker(
            symbol=self._normalize_symbol(symbol),
            market=Market.CN,
            name=name,
            industry="",
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
                log.warning("akshare 行情下载失败，尝试缓存降级: %s", exc)
                if self.cache:
                    bars = self.cache.get(ticker.symbol, start, as_of_date)
                if not bars:
                    raise RuntimeError(
                        f"无法获取 {ticker.symbol} 行情：网络失败且无可用缓存"
                    ) from exc
        bars = [b for b in bars if b.date <= as_of_date]  # 快照语义
        if not bars:
            raise RuntimeError(f"no bars on or before {as_of_date} for {ticker.symbol}")
        prev_close = bars[-2].close if len(bars) > 1 else bars[-1].close
        fundamentals: dict[str, float | str] = {"prev_close": prev_close}
        market_cap: float | None = None
        q = tencent_quote(ticker.symbol)
        if q:
            if q.get("total_market_cap"):
                market_cap = float(q["total_market_cap"])
                fundamentals["total_market_cap_cny"] = market_cap
            if q.get("float_market_cap"):
                fundamentals["float_market_cap_cny"] = float(q["float_market_cap"])
            if q.get("pct_change") is not None:
                fundamentals["pct_change_latest"] = float(q["pct_change"])
        return MarketSnapshot(
            ticker=ticker,
            as_of_date=as_of_date,
            bars=bars,
            last_close=bars[-1].close,
            market_cap=market_cap,
            index="CSI300",
            fundamentals=fundamentals,
            news=[],
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
    def _download_bars(self, symbol: str, start: dt.date, end: dt.date) -> list[OHLCVBar]:
        code = extract_cn_code(symbol)
        if not code:
            raise RuntimeError(f"无法识别 A 股代码: {symbol!r}")
        errors: list[str] = []
        # 1) 腾讯（首选，直连稳定）
        try:
            df = self._ak.stock_zh_a_hist_tx(
                symbol=f"{'sh' if is_shanghai(code) else 'sz'}{code}",
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                adjust="qfq",
            )
            bars = self._bars_from_df(df, symbol, start, end)
            if bars:
                return bars
            errors.append("tx: empty")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"tx: {exc}")
        # 2) 新浪（次选，直连稳定）
        try:
            df = self._ak.stock_zh_a_daily(
                symbol=f"{'sh' if is_shanghai(code) else 'sz'}{code}",
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                adjust="qfq",
            )
            bars = self._bars_from_df(df, symbol, start, end)
            if bars:
                return bars
            errors.append("sina: empty")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"sina: {exc}")
        # 3) 东财（末选，可能与 eastmoney 源同被 RST）
        try:
            with _no_proxy_akshare():
                df = self._ak.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=start.strftime("%Y%m%d"),
                    end_date=end.strftime("%Y%m%d"),
                    adjust="qfq",
                )
            bars = self._bars_from_df(df, symbol, start, end)
            if bars:
                return bars
            errors.append("em: empty")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"em: {exc}")
        raise RuntimeError(
            f"akshare 所有端点均失败 [{symbol} {start}~{end}]: {' | '.join(errors)}"
        )

    @staticmethod
    def _bars_from_df(
        df: pd.DataFrame, symbol: str, start: dt.date, end: dt.date
    ) -> list[OHLCVBar]:
        if df is None or df.empty:
            return []
        # 兼容英文列（tx/新浪）与中文列（东财）两种 akshare 返回。
        if "date" in df.columns:
            date_col, col_o, col_h, col_lo, col_c, col_v = (
                "date", "open", "high", "low", "close", "volume"
            )
        else:
            date_col, col_o, col_h, col_lo, col_c, col_v = (
                "日期", "开盘", "最高", "最低", "收盘", "成交量"
            )
        vol_factor = 100.0 if date_col == "日期" else 1.0  # 东财成交量单位为手
        bars: list[OHLCVBar] = []
        for _, row in df.iterrows():
            day = dt.date.fromisoformat(str(row[date_col])[:10])
            if not (start <= day <= end):
                continue
            bars.append(
                OHLCVBar(
                    date=day,
                    open=float(row[col_o]),
                    high=float(row[col_h]),
                    low=float(row[col_lo]),
                    close=float(row[col_c]),
                    volume=int(float(row[col_v]) * vol_factor),
                )
            )
        return bars

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        code = extract_cn_code(symbol)
        if not code:
            return symbol.upper()
        return f"{code}.{'SS' if is_shanghai(code) else 'SZ'}"
