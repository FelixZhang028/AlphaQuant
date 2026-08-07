"""iFinD SDK provider adapter.

The adapter keeps the proprietary SDK optional: importing the project does not
require iFinD to be installed, and authentication happens lazily on first use.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date
from typing import Any

import pandas as pd

from quant_platform.core.exceptions import (
    ConfigurationError,
    DataCapabilityNotSupported,
    DataUnavailableError,
)
from quant_platform.data.interfaces import DataProvider
from quant_platform.data.normalizers import canonical_symbol


class IFindDataProvider(DataProvider):
    """Fetch A-share history and calendars through the official iFinD SDK."""

    name = "ifind"
    _INDICATORS = "open,high,low,close,volume,amount"

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        *,
        client: Any | None = None,
        batch_size: int = 3,
    ) -> None:
        if batch_size < 1:
            raise ValueError("iFinD batch_size must be at least 1")
        self.username = username
        self.password = password
        self.batch_size = batch_size
        self._client = client
        self._authenticated = client is not None and not username and not password

    def get_security_master(self) -> pd.DataFrame:
        raise DataCapabilityNotSupported(
            "iFinD security-master fields are not enabled; use the AkShare fallback"
        )

    def get_trade_calendar(self, start_date: date, end_date: date) -> pd.DataFrame:
        response = self._call(
            "THS_DateQuery",
            "SSE",
            "dateType:0,period:D,dateFormat:0",
            start_date.isoformat(),
            end_date.isoformat(),
        )
        frame = self._response_to_frame(response, "THS_DateQuery")
        if frame.empty:
            return pd.DataFrame(columns=["cal_date", "is_open", "exchange", "source"])
        date_column = self._find_column(frame, ("time", "date", "cal_date", "trade_date"))
        if date_column is None:
            if frame.shape[1] != 1:
                raise DataUnavailableError("iFinD trade calendar has no recognizable date field")
            date_column = str(frame.columns[0])
        result = pd.DataFrame(
            {
                "cal_date": pd.to_datetime(frame[date_column], errors="coerce").dt.normalize(),
                "is_open": 1,
                "exchange": "SSE",
                "source": self.name,
            }
        ).dropna(subset=["cal_date"])
        return result.drop_duplicates("cal_date").sort_values("cal_date").reset_index(drop=True)

    def get_daily_bars(
        self, trade_date: date, symbols: list[str] | None = None
    ) -> pd.DataFrame:
        if not symbols:
            raise ValueError("iFinD daily bars require an explicit symbol list")
        return self.get_history_range(symbols, trade_date, trade_date, cps=1)

    def get_adjustment_factors(
        self, trade_date: date, symbols: list[str] | None = None
    ) -> pd.DataFrame:
        if not symbols:
            raise ValueError("iFinD adjustment factors require an explicit symbol list")
        from quant_platform.data.normalizers import normalize_ifind_daily

        raw = normalize_ifind_daily(
            self.get_history_range(symbols, trade_date, trade_date, cps=1)
        )
        adjusted = normalize_ifind_daily(
            self.get_history_range(symbols, trade_date, trade_date, cps=2)
        )
        keys = ["symbol", "trade_date"]
        result = raw[keys + ["raw_close"]].merge(
            adjusted[keys + ["raw_close"]].rename(columns={"raw_close": "adjusted_close"}),
            on=keys,
            how="inner",
        )
        denominator = pd.to_numeric(result["raw_close"], errors="coerce").replace(0, pd.NA)
        result["adj_factor"] = pd.to_numeric(
            result["adjusted_close"], errors="coerce"
        ) / denominator
        return result[keys + ["adj_factor"]]

    def get_price_limits(
        self, trade_date: date, symbols: list[str] | None = None
    ) -> pd.DataFrame:
        raise DataCapabilityNotSupported(
            "iFinD price-limit fields are not enabled in this adapter"
        )

    def get_suspensions(
        self, trade_date: date, symbols: list[str] | None = None
    ) -> pd.DataFrame:
        raise DataCapabilityNotSupported(
            "iFinD suspension fields are not enabled in this adapter"
        )

    def get_history_range(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
        *,
        cps: int,
    ) -> pd.DataFrame:
        """Fetch an unadjusted (CPS=1) or forward-adjusted (CPS=2) range."""

        if cps not in {1, 2}:
            raise ValueError("This adapter supports only CPS=1 and CPS=2")
        frames: list[pd.DataFrame] = []
        for batch in self._batches(symbols):
            response = self._call(
                "THS_HQ",
                ",".join(batch),
                self._INDICATORS,
                f"Interval:D,CPS:{cps},Fill:Omit,Currency:MHB",
                start_date.isoformat(),
                end_date.isoformat(),
            )
            frame = self._response_to_frame(response, "THS_HQ")
            if not frame.empty:
                frames.append(self._ensure_symbol_column(frame, batch))
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                import iFinDPy
            except ImportError as exc:
                raise ConfigurationError(
                    "iFinD SDK is not installed. Install the official Windows SDK first."
                ) from exc
            self._client = iFinDPy
        if not self._authenticated:
            if not self.username or not self.password:
                raise ConfigurationError(
                    "iFinD credentials are missing; set IFIND_USERNAME and IFIND_PASSWORD"
                )
            login = getattr(self._client, "THS_iFinDLogin", None)
            if login is None:
                raise ConfigurationError("The installed iFinD SDK has no THS_iFinDLogin")
            response = login(self.username, self.password)
            code = self._error_code(response)
            if code not in {None, 0, -201}:
                raise DataUnavailableError(f"iFinD login failed with error code {code}")
            self._authenticated = True
        return self._client

    def _call(self, method: str, *args: Any) -> Any:
        client = self._ensure_client()
        function = getattr(client, method, None)
        if function is None:
            raise ConfigurationError(f"The installed iFinD SDK has no {method}")
        try:
            response = function(*args)
        except Exception as exc:
            raise DataUnavailableError(f"iFinD {method} request failed: {exc}") from exc
        code = self._error_code(response)
        if code not in {None, 0}:
            message = self._error_message(response)
            suffix = f": {message}" if message else ""
            raise DataUnavailableError(f"iFinD {method} returned error {code}{suffix}")
        return response

    def _batches(self, symbols: list[str]) -> Iterable[list[str]]:
        normalized = [canonical_symbol(symbol) for symbol in symbols]
        for index in range(0, len(normalized), self.batch_size):
            yield normalized[index : index + self.batch_size]

    @classmethod
    def _response_to_frame(cls, response: Any, method: str) -> pd.DataFrame:
        value = response
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise DataUnavailableError(f"iFinD {method} returned invalid JSON") from exc
        if isinstance(value, pd.DataFrame):
            return value.copy()
        if isinstance(value, dict):
            for key in ("tables", "data", "table"):
                if key in value:
                    return cls._tabular_value(value[key])
            return cls._tabular_value(value)
        for name in ("tables", "data", "table"):
            if hasattr(value, name):
                return cls._tabular_value(getattr(value, name))
        raise DataUnavailableError(f"iFinD {method} returned an unsupported response type")

    @classmethod
    def _tabular_value(cls, value: Any) -> pd.DataFrame:
        if isinstance(value, pd.DataFrame):
            return value.copy()
        if isinstance(value, dict):
            for key in ("tables", "table", "data"):
                if key in value:
                    frame = cls._tabular_value(value[key])
                    return cls._attach_metadata(frame, value)
            try:
                return pd.DataFrame(value)
            except ValueError:
                return pd.DataFrame([value])
        if isinstance(value, list):
            if not value:
                return pd.DataFrame()
            if all(isinstance(item, dict) for item in value):
                nested: list[pd.DataFrame] = []
                for item in value:
                    table = item.get("table")
                    if table is None:
                        table = item.get("data")
                    if table is None:
                        nested = []
                        break
                    frame = cls._tabular_value(table)
                    nested.append(cls._attach_metadata(frame, item))
                if nested:
                    return pd.concat(nested, ignore_index=True)
                return pd.DataFrame(value)
            return pd.DataFrame(value)
        raise DataUnavailableError("iFinD response contains no tabular data")

    @staticmethod
    def _attach_metadata(frame: pd.DataFrame, metadata: dict[str, Any]) -> pd.DataFrame:
        result = frame.copy()
        symbol = metadata.get("thscode")
        if symbol is None:
            symbol = metadata.get("symbol")
        if symbol is not None and "thscode" not in result.columns:
            result["thscode"] = symbol
        time = metadata.get("time")
        if time is not None and "time" not in result.columns:
            result["time"] = time
        return result

    @staticmethod
    def _error_code(response: Any) -> int | None:
        if isinstance(response, int):
            return response
        value = response.get("errorcode") if isinstance(response, dict) else getattr(
            response, "errorcode", None
        )
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _error_message(response: Any) -> str:
        value = response.get("errmsg") if isinstance(response, dict) else getattr(
            response, "errmsg", ""
        )
        return str(value or "")

    @staticmethod
    def _find_column(frame: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
        columns = {str(column).lower(): str(column) for column in frame.columns}
        return next((columns[name] for name in candidates if name in columns), None)

    @classmethod
    def _ensure_symbol_column(cls, frame: pd.DataFrame, batch: list[str]) -> pd.DataFrame:
        result = frame.copy()
        if cls._find_column(result, ("thscode", "symbol", "code")) is not None:
            return result
        if len(batch) == 1:
            result["thscode"] = batch[0]
            return result
        raise DataUnavailableError("iFinD batch response has no security-code field")
