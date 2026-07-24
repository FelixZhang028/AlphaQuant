"""AkShare fallback provider adapter."""

from __future__ import annotations

from datetime import date

import pandas as pd

from quant_platform.core.exceptions import DataCapabilityNotSupported
from quant_platform.data.interfaces import DataProvider
from quant_platform.data.normalizers import canonical_symbol


class AkShareDataProvider(DataProvider):
    """Fetch public A-share data from AkShare-backed sources."""

    name = "akshare"

    def __init__(self) -> None:
        import akshare as ak

        self._ak = ak

    def get_security_master(self) -> pd.DataFrame:
        frame = self._ak.stock_info_a_code_name().rename(
            columns={"code": "symbol", "name": "name", "代码": "symbol", "名称": "name"}
        )
        frame["ts_code"] = frame["symbol"].astype(str).map(canonical_symbol)
        return frame

    def get_trade_calendar(self, start_date: date, end_date: date) -> pd.DataFrame:
        frame = self._ak.tool_trade_date_hist_sina().rename(
            columns={"trade_date": "cal_date"}
        )
        frame["cal_date"] = pd.to_datetime(frame["cal_date"])
        mask = frame["cal_date"].between(
            pd.Timestamp(start_date), pd.Timestamp(end_date)
        )
        result = frame.loc[mask].copy()
        result["is_open"] = 1
        return result

    def get_daily_bars(
        self, trade_date: date, symbols: list[str] | None = None
    ) -> pd.DataFrame:
        if not symbols:
            raise ValueError("AkShare daily fallback requires an explicit symbol list")
        day = trade_date.strftime("%Y%m%d")
        frames: list[pd.DataFrame] = []
        for symbol in symbols:
            code = symbol.split(".")[0]
            frame = self._ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=day,
                end_date=day,
                adjust="",
            )
            if not frame.empty:
                frames.append(frame)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def get_adjustment_factors(
        self, trade_date: date, symbols: list[str] | None = None
    ) -> pd.DataFrame:
        raise DataCapabilityNotSupported(
            "AkShare adapter does not expose stable adj_factor data"
        )

    def get_price_limits(
        self, trade_date: date, symbols: list[str] | None = None
    ) -> pd.DataFrame:
        raise DataCapabilityNotSupported(
            "AkShare adapter does not expose canonical price limits"
        )

    def get_suspensions(
        self, trade_date: date, symbols: list[str] | None = None
    ) -> pd.DataFrame:
        return self._ak.stock_tfp_em(date=trade_date.strftime("%Y%m%d"))
