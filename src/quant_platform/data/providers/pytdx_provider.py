"""Optional PyTDX adapter for raw Shanghai and Shenzhen daily bars."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from quant_platform.core.exceptions import DataCapabilityNotSupported, DataUnavailableError
from quant_platform.data.interfaces import DataProvider
from quant_platform.data.normalizers import canonical_symbol

logger = logging.getLogger(__name__)

_DAILY_CATEGORY = 9
_MAX_TDX_PAGE_SIZE = 800


@dataclass(frozen=True)
class PyTdxRequestMetrics:
    """Operational metadata for the most recent successful request."""

    server: str
    page_count: int
    received_rows: int


class PyTdxDataProvider(DataProvider):
    """Fetch unadjusted daily bars from a rotating set of TDX quote servers."""

    name = "pytdx"

    def __init__(
        self,
        *,
        servers: Iterable[object] | None = None,
        timeout: float = 3.0,
        retries: int = 1,
        max_servers: int = 8,
        max_pages: int = 20,
        page_size: int = _MAX_TDX_PAGE_SIZE,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.timeout = max(float(timeout), 0.1)
        self.retries = max(int(retries), 1)
        self.max_servers = max(int(max_servers), 1)
        self.max_pages = max(int(max_pages), 1)
        self.page_size = min(max(int(page_size), 1), _MAX_TDX_PAGE_SIZE)
        self.client_factory = client_factory
        self._configured_servers = list(servers) if servers else []
        self._preferred_server: tuple[str, int] | None = None
        self.last_metrics: PyTdxRequestMetrics | None = None

    def get_security_master(self) -> pd.DataFrame:
        raise DataCapabilityNotSupported("PyTDX is not used as the canonical security master")

    def get_trade_calendar(self, start_date: date, end_date: date) -> pd.DataFrame:
        raise DataCapabilityNotSupported("PyTDX does not expose a canonical trade calendar")

    def get_daily_bars(
        self,
        trade_date: date,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        if not symbols:
            raise ValueError("PyTDX daily fetch requires an explicit symbol list")
        frames = [self.get_history_range(symbol, trade_date, trade_date) for symbol in symbols]
        frames = [frame for frame in frames if not frame.empty]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def get_adjustment_factors(
        self,
        trade_date: date,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        raise DataCapabilityNotSupported(
            "PyTDX corporate actions are not yet converted into audited adjustment factors"
        )

    def get_price_limits(
        self,
        trade_date: date,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        raise DataCapabilityNotSupported("PyTDX does not expose canonical daily price limits")

    def get_suspensions(
        self,
        trade_date: date,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        raise DataCapabilityNotSupported(
            "Zero PyTDX volume is not treated as authoritative suspension status"
        )

    def get_history_range(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Fetch enough backward pages to cover a date range and its prior close."""

        if start_date > end_date:
            raise ValueError("start_date cannot be later than end_date")
        market, code = self._market_and_code(symbol)
        failures: list[str] = []
        self.last_metrics = None

        for host, port in self._servers()[: self.max_servers]:
            for attempt in range(1, self.retries + 1):
                api = self._new_client()
                try:
                    connected = api.connect(host, port, time_out=self.timeout)
                    if not connected:
                        raise ConnectionError("connection was rejected")
                    frame, page_count = self._fetch_pages(
                        api,
                        market=market,
                        code=code,
                        start_date=start_date,
                    )
                    if frame.empty:
                        raise DataUnavailableError("server returned no daily bars")
                    frame["requested_symbol"] = canonical_symbol(symbol)
                    self._preferred_server = (host, port)
                    self.last_metrics = PyTdxRequestMetrics(
                        server=f"{host}:{port}",
                        page_count=page_count,
                        received_rows=len(frame),
                    )
                    return frame
                except Exception as exc:
                    failures.append(
                        f"{host}:{port} attempt {attempt}: {type(exc).__name__}: {exc}"
                    )
                    logger.warning(
                        "PyTDX request failed via %s:%s (attempt %s): %s",
                        host,
                        port,
                        attempt,
                        exc,
                    )
                finally:
                    try:
                        api.disconnect()
                    except Exception:
                        logger.debug("PyTDX disconnect failed", exc_info=True)

        detail = "; ".join(failures[-6:])
        raise DataUnavailableError(f"PyTDX exhausted available quote servers; {detail}")

    def _fetch_pages(
        self,
        api: Any,
        *,
        market: int,
        code: str,
        start_date: date,
    ) -> tuple[pd.DataFrame, int]:
        frames: list[pd.DataFrame] = []
        previous_signature: tuple[object, ...] | None = None
        page_count = 0

        for page_index in range(self.max_pages):
            offset = page_index * self.page_size
            payload = api.get_security_bars(
                _DAILY_CATEGORY,
                market,
                code,
                offset,
                self.page_size,
            )
            if payload is None:
                raise DataUnavailableError(f"PyTDX returned None at offset {offset}")
            page = pd.DataFrame(payload)
            if page.empty:
                break
            page_dates = self._page_dates(page)
            valid_dates = page_dates.dropna()
            if valid_dates.empty:
                raise DataUnavailableError("PyTDX returned bars without parseable dates")
            close_values = (
                pd.to_numeric(page["close"], errors="coerce")
                if "close" in page.columns
                else pd.Series(0.0, index=page.index)
            )
            signature = (
                len(page),
                valid_dates.min(),
                valid_dates.max(),
                float(close_values.sum()),
            )
            if signature == previous_signature:
                raise DataUnavailableError("PyTDX repeated a page while paginating")
            previous_signature = signature
            frames.append(page)
            page_count += 1

            if valid_dates.min().date() < start_date or len(page) < self.page_size:
                break
        else:
            raise DataUnavailableError(
                f"PyTDX history exceeded the configured {self.max_pages} page limit"
            )

        if not frames:
            return pd.DataFrame(), page_count
        combined = pd.concat(frames, ignore_index=True)
        return combined.drop_duplicates().reset_index(drop=True), page_count

    @staticmethod
    def _page_dates(frame: pd.DataFrame) -> pd.Series:
        if "datetime" in frame.columns:
            return pd.to_datetime(frame["datetime"], errors="coerce").dt.normalize()
        if "date" in frame.columns:
            return pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
        required = {"year", "month", "day"}
        if required.issubset(frame.columns):
            return pd.to_datetime(
                frame[["year", "month", "day"]].rename(
                    columns={"year": "year", "month": "month", "day": "day"}
                ),
                errors="coerce",
            ).dt.normalize()
        return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")

    @staticmethod
    def _market_and_code(symbol: str) -> tuple[int, str]:
        normalized = canonical_symbol(symbol)
        code, exchange = normalized.split(".")
        if exchange == "SH":
            return 1, code
        if exchange == "SZ":
            return 0, code
        raise DataCapabilityNotSupported(
            f"PyTDX first-stage adapter supports SH/SZ only, received {normalized}"
        )

    def _servers(self) -> list[tuple[str, int]]:
        raw_servers = self._configured_servers or self._default_servers()
        servers: list[tuple[str, int]] = []
        for value in raw_servers:
            parsed = self._parse_server(value)
            if parsed is not None and parsed not in servers:
                servers.append(parsed)
        if not servers:
            raise DataUnavailableError("No valid PyTDX quote servers are configured")
        if self._preferred_server in servers:
            servers.remove(self._preferred_server)
            servers.insert(0, self._preferred_server)
        return servers

    @staticmethod
    def _parse_server(value: object) -> tuple[str, int] | None:
        if isinstance(value, str):
            host, separator, port = value.rpartition(":")
            if separator and host and port.isdigit():
                return host, int(port)
            return None
        if isinstance(value, Mapping):
            host = value.get("host", value.get("ip"))
            port = value.get("port", 7709)
            if host:
                return str(host), int(port)
            return None
        if isinstance(value, (tuple, list)):
            if len(value) >= 3:
                return str(value[-2]), int(value[-1])
            if len(value) == 2:
                return str(value[0]), int(value[1])
        return None

    @staticmethod
    def _default_servers() -> list[object]:
        try:
            from pytdx.config.hosts import hq_hosts
        except ImportError as exc:
            raise DataUnavailableError(
                "PyTDX is not installed; install the optional 'tdx' dependency"
            ) from exc
        return list(hq_hosts)

    def _new_client(self) -> Any:
        if self.client_factory is not None:
            return self.client_factory()
        try:
            from pytdx.hq import TdxHq_API
        except ImportError as exc:
            raise DataUnavailableError(
                "PyTDX is not installed; install the optional 'tdx' dependency"
            ) from exc
        return TdxHq_API(auto_retry=False, raise_exception=True)
