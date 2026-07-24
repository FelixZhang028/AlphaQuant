"""Tushare Pro provider adapter."""

from __future__ import annotations

from datetime import date

import pandas as pd

from quant_platform.data.interfaces import DataProvider


class TushareDataProvider(DataProvider):
    """Fetch source-native A-share datasets from Tushare Pro."""

    name = "tushare"

    def __init__(self, token: str) -> None:
        if not token:
            raise ValueError("Tushare token is required")
        import tushare as ts

        self._pro = ts.pro_api(token)

    def get_security_master(self) -> pd.DataFrame:
        frames = [
            self._pro.stock_basic(list_status=status) for status in ("L", "D", "P")
        ]
        return pd.concat(frames, ignore_index=True).drop_duplicates(
            "ts_code", keep="last"
        )

    def get_trade_calendar(self, start_date: date, end_date: date) -> pd.DataFrame:
        return self._pro.trade_cal(
            exchange="SSE",
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )

    def get_daily_bars(
        self, trade_date: date, symbols: list[str] | None = None
    ) -> pd.DataFrame:
        symbol_arg = ",".join(symbols) if symbols else None
        return self._pro.daily(
            ts_code=symbol_arg, trade_date=trade_date.strftime("%Y%m%d")
        )

    def get_adjustment_factors(
        self, trade_date: date, symbols: list[str] | None = None
    ) -> pd.DataFrame:
        symbol_arg = ",".join(symbols) if symbols else None
        return self._pro.adj_factor(
            ts_code=symbol_arg, trade_date=trade_date.strftime("%Y%m%d")
        )

    def get_price_limits(
        self, trade_date: date, symbols: list[str] | None = None
    ) -> pd.DataFrame:
        symbol_arg = ",".join(symbols) if symbols else None
        return self._pro.stk_limit(
            ts_code=symbol_arg, trade_date=trade_date.strftime("%Y%m%d")
        )

    def get_suspensions(
        self, trade_date: date, symbols: list[str] | None = None
    ) -> pd.DataFrame:
        symbol_arg = ",".join(symbols) if symbols else None
        return self._pro.suspend_d(
            ts_code=symbol_arg,
            trade_date=trade_date.strftime("%Y%m%d"),
            suspend_type="S",
        )
