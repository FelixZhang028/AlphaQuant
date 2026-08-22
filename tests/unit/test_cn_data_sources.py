"""单元测试：A 股数据源（东财修复 / akshare / 同花顺 / 降级链）。

注意：不用 pytest 的 tmp_path fixture（DSH 沙箱禁止其 .lock 创建），
临时目录用 Path.mkdir 自行创建并在 teardown 清理。
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from trading_agents.data.akshare_provider import AkshareProvider
from trading_agents.data.eastmoney import (
    EastMoneyProvider,
    extract_jsonp_array,
    normalize_secid,
    normalize_symbol,
    sina_symbol,
)
from trading_agents.data.fallback import FallbackProvider
from trading_agents.data.tonghuashun import TonghuashunProvider
from trading_agents.schemas import MarketSnapshot, Ticker
from trading_agents.schemas.models import Market

# ------------------------------------------------------------ 东财工具 ----

class TestNormalize:
    def test_secid_shenzhen(self) -> None:
        assert normalize_secid("002466") == "0.002466"
        assert normalize_secid("002466.SZ") == "0.002466"
        assert normalize_secid("sz002466") == "0.002466"

    def test_secid_shanghai(self) -> None:
        assert normalize_secid("600519") == "1.600519"
        assert normalize_secid("688981.SS") == "1.688981"

    def test_secid_invalid(self) -> None:
        with pytest.raises(ValueError):
            normalize_secid("AAPL")

    def test_normalize_symbol(self) -> None:
        assert normalize_symbol("002466") == "002466.SZ"
        assert normalize_symbol("600519.SS") == "600519.SS"

    def test_sina_symbol(self) -> None:
        assert sina_symbol("002466") == "sz002466"
        assert sina_symbol("600519") == "sh600519"


class TestExtractJsonpArray:
    def test_plain_payload(self) -> None:
        text = 'x([{"day": "2024-01-02", "open": "1.0"}])'
        assert extract_jsonp_array(text) == [{"day": "2024-01-02", "open": "1.0"}]

    def test_comment_prefix(self) -> None:
        # 新浪新版响应带反盗链注释前缀
        text = (
            "/*<script>location.href=\\'//sina.com\\';</script>*/\n"
            'x([{"day": "2024-01-02", "open": "1.0"}])'
        )
        assert extract_jsonp_array(text) == [{"day": "2024-01-02", "open": "1.0"}]

    def test_redirect_script_only(self) -> None:
        # 反盗链时只返回重定向脚本（无括号无数据）→ None
        text = "/*<script>location.href=\\'//sina.com\\';</script>*/"
        assert extract_jsonp_array(text) is None

    def test_garbage(self) -> None:
        assert extract_jsonp_array("<html>403 Forbidden</html>") is None


# ------------------------------------------------------------ 东财传输 ----

class _FakeResponse:
    def __init__(self, status: int = 200, body: str = "{}") -> None:
        self.status_code = status
        self._body = body
        self.text = body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        import json
        return json.loads(self._body)


class _FakeSession:
    """记录调用并可按配置失败/成功的伪 requests.Session。"""

    def __init__(self, results: list) -> None:
        self._results = list(results)
        self.calls: list[tuple[str, dict]] = []
        self.trust_env = True

    def get(self, url: str, params: dict | None = None, headers=None, timeout=None):
        self.calls.append((url, params or {}))
        if not self._results:
            raise RuntimeError("no more canned responses")
        item = self._results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class TestTransportChannelIsolation:
    """跨接口通道隔离：缓存的可用通道不得被复用到其他 API 路径。"""

    def _provider(self, results: list) -> EastMoneyProvider:
        p = EastMoneyProvider.__new__(EastMoneyProvider)
        p._transport = object.__new__(type(p)._Transport if False else object)  # placeholder
        return p

    def test_working_channel_scoped_to_path(self) -> None:
        from trading_agents.data.eastmoney import _Transport

        t = _Transport()
        # 先让 push2delay 报价通道成功 → 缓存 _working
        ok_quote = _FakeResponse(200, '{"data": {"f58": "测试"}}')
        s1 = _FakeSession([ok_quote])
        t._channels = [("https", s1)]
        r = t.get_json("push2delay.eastmoney.com/api/qt/stock/get",
                       {"secid": "0.002466"}, ok=lambda r: bool(r.json().get("data")))
        assert r is ok_quote
        assert t._working == ("push2delay.eastmoney.com/api/qt/stock/get", "https", s1)

        # 请求不同路径（如新浪）时，不得复用 push2delay 通道（否则参数打错主机）
        s2 = _FakeSession([_FakeResponse(200, "x([1])")])
        t._channels = [("https", s2)]
        r2 = t.get_json("quotes.sina.cn/cn/api/x",
                        {"symbol": "sz002466"}, headers={"User-Agent": "t"})
        assert r2.status_code == 200
        # 第一个尝试的必须是新浪自身通道，而不是缓存里的 push2delay
        assert s2.calls[0][0] == "https://quotes.sina.cn/cn/api/x"

    def test_ok_callback_treats_empty_as_failure(self) -> None:
        from trading_agents.data.eastmoney import _Transport

        t = _Transport()
        empty = _FakeResponse(200, '{"data": {"klines": []}}')
        good = _FakeResponse(200, '{"data": {"klines": ["20240102,1,2,3,4,5"]}}')
        s = _FakeSession([empty, good])
        t._channels = [("http", s)]
        r = t.get_json("push2his.eastmoney.com/api/qt/stock/kline/get",
                       {"secid": "0.002466"},
                       ok=lambda r: bool((r.json().get("data") or {}).get("klines")))
        assert r is good
        assert len(s.calls) == 2  # 空内容被判定失败，继续下一通道

    def test_all_channels_fail_then_retry(self) -> None:
        from trading_agents.data.eastmoney import _Transport

        t = _Transport(retries=1)
        fail = RuntimeError("network down")
        good = _FakeResponse(200, '{"data": {}}')
        # 单通道：第 1 轮失败 → 整体重试第 2 轮成功（共 2 次调用）
        s = _FakeSession([fail, good])
        t._channels = [("http", s)]
        r = t.get_json("h.x.com/a", {"k": 1})
        assert r.status_code == 200
        assert len(s.calls) == 2  # 第 1 轮失败 + 重试轮成功


# ------------------------------------------------------------ 同花顺解析 ----

class TestTonghuashunParsing:
    def test_fetch_year_parses_data_string(self) -> None:
        p = TonghuashunProvider.__new__(TonghuashunProvider)

        payload = (
            'quotebridge_v6_line_hs_002466_01_2025({"data":"'
            "20250603,28.80,29.68,28.70,29.32,13282784,387990960.00,0.900,,,0;"
            "20250604,29.35,30.57,29.32,30.37,35625856,1076004970.00,2.414,,,0"
            '"})'
        )

        class _R:
            text = payload

            def raise_for_status(self) -> None:
                pass

        class _S:
            def get(self, url, timeout=None):
                assert "hs_002466/01/2025.js" in url
                return _R()

        p._session = _S()
        bars = p._fetch_year("hs_002466", 2025)
        assert len(bars) == 2
        assert bars[0].date == dt.date(2025, 6, 3)
        assert bars[0].open == 28.80
        assert bars[0].high == 29.68
        assert bars[0].low == 28.70
        assert bars[0].close == 29.32
        assert bars[0].volume == 13282784  # 股（与腾讯 qfq 同单位）

    def test_ths_symbol_normalization(self) -> None:
        from trading_agents.data.cn_quote import ths_symbol

        assert ths_symbol("002466.SZ") == "hs_002466"
        assert ths_symbol("600519") == "sh_600519"


# ------------------------------------------------------------ akshare 解析 ----

class TestAkshareBarsFromDf:
    def test_english_columns(self) -> None:
        import pandas as pd

        df = pd.DataFrame(
            {
                "date": ["2025-06-03", "2025-06-04"],
                "open": [28.8, 29.35],
                "high": [29.68, 30.57],
                "low": [28.7, 29.32],
                "close": [29.32, 30.37],
                "volume": [13282800, 35625900],
            }
        )
        bars = AkshareProvider._bars_from_df(
            df, "002466", dt.date(2025, 6, 3), dt.date(2025, 6, 4)
        )
        assert len(bars) == 2
        assert bars[0].close == 29.32
        assert bars[0].volume == 13282800

    def test_chinese_columns_volume_lots(self) -> None:
        import pandas as pd

        df = pd.DataFrame(
            {
                "日期": ["2025-06-03"],
                "开盘": [28.8],
                "最高": [29.68],
                "最低": [28.7],
                "收盘": [29.32],
                "成交量": [132828.0],  # 东财单位：手 → ×100
            }
        )
        bars = AkshareProvider._bars_from_df(
            df, "002466", dt.date(2025, 6, 3), dt.date(2025, 6, 4)
        )
        assert len(bars) == 1
        assert bars[0].volume == 13282800

    def test_filters_by_range(self) -> None:
        import pandas as pd

        df = pd.DataFrame(
            {
                "date": ["2025-06-02", "2025-06-03"],
                "open": [1.0, 2.0],
                "high": [1.1, 2.1],
                "low": [0.9, 1.9],
                "close": [1.05, 2.05],
                "volume": [100, 200],
            }
        )
        bars = AkshareProvider._bars_from_df(
            df, "X", dt.date(2025, 6, 3), dt.date(2025, 6, 3)
        )
        assert len(bars) == 1
        assert bars[0].date == dt.date(2025, 6, 3)


# ------------------------------------------------------------ 降级链 ----

class _BoomProvider:
    name = "boom"

    def resolve(self, symbol, market):
        raise RuntimeError("boom resolve")

    def get_snapshot(self, ticker, as_of_date, lookback_days=60):
        raise RuntimeError("boom snapshot")

    def get_bars_after(self, ticker, start, days):
        raise RuntimeError("boom bars_after")


class _OkProvider:
    name = "ok"

    def __init__(self) -> None:
        self.resolve_calls = 0
        self.snapshot_calls = 0

    def resolve(self, symbol, market):
        self.resolve_calls += 1
        return Ticker(symbol=symbol.upper(), market=Market(market), name="ok")

    def get_snapshot(self, ticker, as_of_date, lookback_days=60):
        self.snapshot_calls += 1
        return MarketSnapshot(
            ticker=ticker, as_of_date=as_of_date, bars=[], last_close=1.0
        )

    def get_bars_after(self, ticker, start, days):
        return []


class TestFallbackProvider:
    def test_tries_in_order_and_skips_failures(self) -> None:
        ok = _OkProvider()
        fp = FallbackProvider([_BoomProvider(), ok])
        t = fp.resolve("aapl", "US")
        assert t.name == "ok"
        assert ok.resolve_calls == 1
        assert fp.active_source == "ok"

    def test_all_fail_raises(self) -> None:
        fp = FallbackProvider([_BoomProvider(), _BoomProvider()])
        with pytest.raises(RuntimeError, match="所有数据源均失败"):
            fp.resolve("aapl", "US")

    def test_empty_provider_list_rejected(self) -> None:
        with pytest.raises(ValueError):
            FallbackProvider([])


# ------------------------------------------------------------ CLI 装配 ----

class TestCliBuildsNewSources:
    """CLI 装配：akshare/tonghuashun/auto 可构造且为正确类型。

    临时目录用 Path.mkdir 自建（DSH 沙箱下 pytest tmp_path 不可用）。
    """

    def setup_method(self) -> None:
        base = Path.cwd() / ".cn_data_src_tmp" / "cli_sources"
        base.mkdir(parents=True, exist_ok=True)
        self._base = base

    def teardown_method(self) -> None:
        import shutil
        shutil.rmtree(self._base, ignore_errors=True)

    def test_builds_new_sources(self) -> None:
        from trading_agents.cli import build_context
        from trading_agents.config import TradingConfig

        cfg = TradingConfig.load(base_dir=self._base / "runs")
        ctx = build_context(cfg, "akshare")
        assert isinstance(ctx.provider, AkshareProvider)
        ctx = build_context(cfg, "tonghuashun")
        assert isinstance(ctx.provider, TonghuashunProvider)
        ctx = build_context(cfg, "auto")
        assert isinstance(ctx.provider, FallbackProvider)
        assert [p.name for p in ctx.provider.providers] == [
            "eastmoney", "akshare", "tonghuashun",
        ]
