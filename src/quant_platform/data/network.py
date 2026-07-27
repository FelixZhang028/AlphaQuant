"""Network safeguards and endpoint fallbacks for AkShare."""

from __future__ import annotations

import functools
import logging
import os
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

_PROXY_KEYS = {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"}
_BYPASS_KEYS = {"NO_PROXY"}
_environment_lock = threading.RLock()


class AkShareNetworkError(RuntimeError):
    """AkShare could not be reached through primary or fallback endpoints."""


def is_proxy_error(error: BaseException) -> bool:
    """Return whether an exception chain represents a failed HTTP proxy."""

    return _exception_matches(
        error,
        class_names={"ProxyError"},
        markers=("unable to connect to proxy", "proxyerror"),
    )


def is_connection_error(error: BaseException) -> bool:
    """Return whether an exception chain represents a transport failure."""

    return _exception_matches(
        error,
        class_names={"ConnectionError", "ProxyError", "RemoteDisconnected"},
        markers=(
            "unable to connect",
            "connection aborted",
            "connection reset",
            "remote end closed",
            "max retries exceeded",
            "timed out",
        ),
    )


def _exception_matches(
    error: BaseException,
    *,
    class_names: set[str],
    markers: tuple[str, ...],
) -> bool:
    pending: list[BaseException] = [error]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        if type(current).__name__ in class_names or any(
            marker in str(current).lower() for marker in markers
        ):
            return True
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return False


@contextmanager
def without_proxy_environment() -> Iterator[None]:
    """Temporarily bypass environment and Windows system proxies."""

    with _environment_lock:
        managed_keys = _PROXY_KEYS | _BYPASS_KEYS
        matching_keys = [
            key for key in list(os.environ) if key.upper() in managed_keys
        ]
        original = {key: os.environ[key] for key in matching_keys}
        for key in matching_keys:
            os.environ.pop(key, None)
        # This also bypasses Windows Internet Settings proxies, which urllib
        # still discovers after HTTP_PROXY and HTTPS_PROXY are removed.
        os.environ["NO_PROXY"] = "*"
        try:
            yield
        finally:
            for key in list(os.environ):
                if key.upper() in managed_keys:
                    os.environ.pop(key, None)
            os.environ.update(original)


class ProxyResilientAkShareClient:
    """Use direct access and Sina when AkShare's Eastmoney route is unavailable."""

    def __init__(self, client: Any, *, direct_fallback: bool = True) -> None:
        self._client = client
        self._direct_fallback = direct_fallback
        self._prefer_direct = False

    @property
    def direct_fallback_active(self) -> bool:
        """Return whether a broken proxy has already been detected."""

        return self._prefer_direct

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._client, name)
        if not callable(attribute):
            return attribute

        @functools.wraps(attribute)
        def call(*args: Any, **kwargs: Any) -> Any:
            return self._call(name, attribute, *args, **kwargs)

        return call

    def _call(
        self,
        name: str,
        operation: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        if self._prefer_direct:
            try:
                return self._call_direct(operation, *args, **kwargs)
            except Exception as direct_error:
                return self._fallback_or_raise(name, direct_error, **kwargs)

        try:
            return operation(*args, **kwargs)
        except Exception as first_error:
            if not self._direct_fallback or not is_connection_error(first_error):
                raise
            self._prefer_direct = True
            logger.warning(
                "AkShare connection failed; retrying without proxy environment"
            )
            try:
                return self._call_direct(operation, *args, **kwargs)
            except Exception as direct_error:
                return self._fallback_or_raise(name, direct_error, **kwargs)

    @staticmethod
    def _call_direct(
        operation: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        with without_proxy_environment():
            return operation(*args, **kwargs)

    def _fallback_or_raise(
        self, name: str, direct_error: Exception, **parameters: Any
    ) -> Any:
        try:
            if name == "stock_zh_a_hist":
                logger.warning("Eastmoney stock bars unavailable; using Sina fallback")
                return self._sina_stock_history(parameters)
            if name == "index_zh_a_hist":
                logger.warning("Eastmoney index bars unavailable; using Sina fallback")
                return self._sina_index_history(parameters)
        except Exception as fallback_error:
            raise AkShareNetworkError(
                "东方财富接口不可用，新浪备用接口也未能返回数据；"
                "请检查网络、防火墙或本机代理设置。"
            ) from fallback_error
        raise AkShareNetworkError(
            "代理连接失败，自动绕过代理直连后仍无法访问 AkShare 数据源；"
            "请检查网络、防火墙或本机代理设置。"
        ) from direct_error

    def _sina_stock_history(self, parameters: dict[str, Any]) -> pd.DataFrame:
        code = str(parameters["symbol"]).split(".", maxsplit=1)[0].zfill(6)
        if code.startswith(("4", "8")):
            exchange = "bj"
        elif code.startswith(("5", "6", "9")):
            exchange = "sh"
        else:
            exchange = "sz"
        operation = self._client.stock_zh_a_daily
        with without_proxy_environment():
            raw = pd.DataFrame(
                operation(
                    symbol=f"{exchange}{code}",
                    start_date=str(parameters["start_date"]),
                    end_date=str(parameters["end_date"]),
                    adjust=str(parameters.get("adjust", "")),
                )
            )
        result = raw.rename(
            columns={
                "date": "日期",
                "open": "开盘",
                "high": "最高",
                "low": "最低",
                "close": "收盘",
                "volume": "成交量",
                "amount": "成交额",
            }
        ).copy()
        result["股票代码"] = code
        if "成交量" in result:
            result["成交量"] = pd.to_numeric(
                result["成交量"], errors="coerce"
            ) / 100.0
        if "成交额" not in result:
            result["成交额"] = pd.NA
        return result

    def _sina_index_history(self, parameters: dict[str, Any]) -> pd.DataFrame:
        code = str(parameters["symbol"]).split(".", maxsplit=1)[0].zfill(6)
        exchange = "sz" if code.startswith("399") else "sh"
        operation = self._client.stock_zh_index_daily
        with without_proxy_environment():
            raw = pd.DataFrame(operation(symbol=f"{exchange}{code}"))
        raw["date"] = pd.to_datetime(raw["date"])
        start_date = pd.to_datetime(str(parameters["start_date"]))
        end_date = pd.to_datetime(str(parameters["end_date"]))
        raw = raw.loc[raw["date"].between(start_date, end_date)]
        return raw.rename(
            columns={
                "date": "日期",
                "open": "开盘",
                "high": "最高",
                "low": "最低",
                "close": "收盘",
                "volume": "成交量",
                "amount": "成交额",
            }
        )


def friendly_data_error(error: Exception) -> str:
    """Turn low-level network failures into a short user-facing message."""

    message = str(error)
    lowered = message.lower()
    if isinstance(error, AkShareNetworkError) or any(
        marker in lowered
        for marker in (
            "aksharenetworkerror",
            "proxyerror",
            "unable to connect to proxy",
            "connectionerror",
            "remotedisconnected",
        )
    ):
        return (
            "无法连接 AkShare 数据源。程序已尝试绕过代理，并切换备用接口；"
            "请确认网络正常，或检查 HTTP_PROXY/HTTPS_PROXY 设置。"
        )
    compact = " ".join(message.split())
    return f"{type(error).__name__}: {compact}"[:500]
