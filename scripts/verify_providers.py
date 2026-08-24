"""验证：三个 A 股数据源 + 降级链（临时脚本）。"""

import sys
import datetime as dt

sys.path.insert(0, "src")

from trading_agents.data.akshare_provider import AkshareProvider
from trading_agents.data.eastmoney import EastMoneyProvider
from trading_agents.data.fallback import FallbackProvider
from trading_agents.data.tonghuashun import TonghuashunProvider


def main() -> None:
    trade_date = dt.date(2025, 6, 3)
    print(f"分析日期: {trade_date}")

    for cls in (EastMoneyProvider, AkshareProvider, TonghuashunProvider):
        print(f"\n=== {cls.__name__} ===")
        try:
            p = cls()
            t = p.resolve("002466", "CN")
            print(f"resolve -> {t.name} ({t.symbol})")
            snap = p.get_snapshot(t, trade_date, lookback_days=60)
            print(f"snapshot -> bars={len(snap.bars)} last_close={snap.last_close} "
                  f"market_cap={snap.market_cap}")
            if snap.bars:
                last = snap.bars[-1]
                print(f"  最后一根: {last.date} O={last.open} H={last.high} "
                      f"L={last.low} C={last.close} V={last.volume}")
        except Exception as exc:
            print(f"FAIL: {type(exc).__name__}: {exc}")

    print("\n=== FallbackProvider (auto) ===")
    try:
        p = FallbackProvider([
            EastMoneyProvider(),
            AkshareProvider(),
            TonghuashunProvider(),
        ])
        t = p.resolve("002466", "CN")
        print(f"resolve -> {t.name} ({t.symbol}), active_source={p.active_source}")
        snap = p.get_snapshot(t, trade_date, lookback_days=60)
        print(f"snapshot -> bars={len(snap.bars)} last_close={snap.last_close}, "
              f"active_source={p.active_source}")
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
