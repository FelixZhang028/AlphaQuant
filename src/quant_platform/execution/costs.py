"""Dated A-share fees. Rates exclude broker commission and apply per side."""

from datetime import date


def stamp_rate(day: date) -> float:
    # The supported historical period starts after the sell-only reform.
    if day < date(2008, 9, 19):
        raise ValueError("自动税费仅支持 2008-09-19 起的回测，请显式配置更早税费")
    return 0.0005 if day >= date(2023, 8, 28) else 0.001


def transfer_rate(day: date, symbol: str) -> float:
    if day < date(2015, 8, 1):
        raise ValueError("自动过户费仅支持 2015-08-01 起的回测")
    # SH/SZ A shares; other markets require a supplied schedule.
    if not symbol.endswith((".SH", ".SZ")):
        raise ValueError("自动过户费仅支持沪深 A 股，请为该市场配置过户费率")
    return 0.00001 if day >= date(2022, 4, 29) else 0.00002
