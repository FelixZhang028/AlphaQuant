"""BaoStock provider adapter with explicit login and error handling."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date
from typing import Any

import pandas as pd

from quant_platform.core.exceptions import DataCapabilityNotSupported, DataUnavailableError
from quant_platform.data.interfaces import DataProvider
from quant_platform.data.normalizers import canonical_symbol

_HISTORY_FIELDS = (
    "date,code,open,high,low,close,preclose,volume,amount,adjustflag,"
    "tradestatus,pctChg,isST"
)


class BaoStockDataProvider(DataProvider):
    """Fetch free A-share history and daily status fields from BaoStock."""

    name = "baostock"

    def __init__(self, client: Any | None = None, *, retries: int = 3) -> None:
        if client is None:
            import baostock as bs

            client = bs
        self._client = client
        self._logged_in = False
        self._retries = max(int(retries), 1)

    def login(self) -> None:
        """Open a BaoStock session once and reject provider-side errors."""

        if self._logged_in:
            return
        failures: list[str] = []
        for attempt in range(1, self._retries + 1):
            try:
                result = self._client.login()
                self._check_result(result, "login")
                self._logged_in = True
                return
            except Exception as exc:
                failures.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
                if attempt < self._retries:
                    time.sleep(min(attempt, 2))
        raise DataUnavailableError("BaoStock login failed; " + "; ".join(failures))

    def close(self) -> None:
        """Close an active BaoStock session."""

        if self._logged_in:
            self._client.logout()
            self._logged_in = False

    def get_security_master(self) -> pd.DataFrame:
        self.login()
        return self._query_frame("query_stock_basic", self._client.query_stock_basic)

    def get_security_metadata(self, symbols: list[str]) -> pd.DataFrame:
        """Fetch point-in-time listing metadata for the requested securities."""

        self.login()
        frames: list[pd.DataFrame] = []
        for symbol in symbols:
            frame = self._query_frame(
                "query_stock_basic",
                lambda symbol=symbol: self._client.query_stock_basic(
                    code=self.to_baostock_symbol(symbol)
                ),
            )
            if not frame.empty:
                frames.append(frame)
        if not frames:
            return pd.DataFrame()
        result = pd.concat(frames, ignore_index=True)
        if "code" in result.columns:
            result["symbol"] = result["code"].astype(str).map(canonical_symbol)
        return result.drop_duplicates("symbol", keep="last")

    def get_trade_calendar(self, start_date: date, end_date: date) -> pd.DataFrame:
        self.login()
        return self._query_frame(
            "query_trade_dates",
            lambda: self._client.query_trade_dates(
                start_date=start_date.isoformat(), end_date=end_date.isoformat()
            ),
        )

    def get_history_range(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        *,
        adjustflag: str,
    ) -> pd.DataFrame:
        """Fetch one symbol range; adjustflag 3 is raw and 2 is forward-adjusted."""

        self.login()
        return self._query_frame(
            "query_history_k_data_plus",
            lambda: self._client.query_history_k_data_plus(
                self.to_baostock_symbol(symbol),
                _HISTORY_FIELDS,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                frequency="d",
                adjustflag=adjustflag,
            ),
        )

    def get_daily_bars(self, trade_date: date, symbols: list[str] | None = None) -> pd.DataFrame:
        if not symbols:
            raise ValueError("BaoStock daily fetch requires an explicit symbol list")
        frames = [
            self.get_history_range(symbol, trade_date, trade_date, adjustflag="3")
            for symbol in symbols
        ]
        return pd.concat([frame for frame in frames if not frame.empty], ignore_index=True)

    def get_adjustment_factors(
        self, trade_date: date, symbols: list[str] | None = None
    ) -> pd.DataFrame:
        raise DataCapabilityNotSupported(
            "BaoStock adjustment data is composed by the range-backfill adapter"
        )

    def get_price_limits(self, trade_date: date, symbols: list[str] | None = None) -> pd.DataFrame:
        raise DataCapabilityNotSupported(
            "BaoStock does not expose canonical daily upper/lower limit prices"
        )

    def get_suspensions(self, trade_date: date, symbols: list[str] | None = None) -> pd.DataFrame:
        frame = self.get_daily_bars(trade_date, symbols)
        if frame.empty or "tradestatus" not in frame.columns:
            return pd.DataFrame(columns=["symbol", "trade_date"])
        suspended = frame[frame["tradestatus"].astype(str).eq("0")].copy()
        suspended["symbol"] = suspended["code"].astype(str).map(canonical_symbol)
        suspended["trade_date"] = pd.to_datetime(suspended["date"]).dt.normalize()
        return suspended[["symbol", "trade_date"]]

    @staticmethod
    def to_baostock_symbol(symbol: str) -> str:
        """Convert canonical symbols to BaoStock's ``sh.600000`` form."""

        canonical = canonical_symbol(symbol)
        code, exchange = canonical.split(".")
        return f"{exchange.lower()}.{code}"

    @staticmethod
    def _check_result(result: Any, operation: str) -> None:
        error_code = str(getattr(result, "error_code", "0"))
        if error_code != "0":
            message = str(getattr(result, "error_msg", "unknown provider error"))
            raise DataUnavailableError(f"BaoStock {operation} failed [{error_code}]: {message}")

    @classmethod
    def _result_frame(cls, result: Any, operation: str) -> pd.DataFrame:
        cls._check_result(result, operation)
        frame = result.get_data()
        if not isinstance(frame, pd.DataFrame):
            raise DataUnavailableError(f"BaoStock {operation} returned a non-tabular response")
        return frame

    def _query_frame(self, operation: str, request: Callable[[], Any]) -> pd.DataFrame:
        failures: list[str] = []
        for attempt in range(1, self._retries + 1):
            try:
                return self._result_frame(request(), operation)
            except Exception as exc:
                failures.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
                if attempt < self._retries:
                    time.sleep(min(attempt, 2))
        raise DataUnavailableError(f"BaoStock {operation} failed; " + "; ".join(failures))
