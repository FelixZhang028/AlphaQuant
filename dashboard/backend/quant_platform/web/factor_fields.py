"""Shared Chinese labels and explanations for factor inputs."""

FIELD_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "raw_open": ("开盘价（未复权）", "当日开盘成交价，未作分红、送转等复权调整。"),
    "raw_high": ("最高价（未复权）", "当日最高成交价，未作分红、送转等复权调整。"),
    "raw_low": ("最低价（未复权）", "当日最低成交价，未作分红、送转等复权调整。"),
    "raw_close": ("收盘价（未复权）", "当日收盘成交价，未作分红、送转等复权调整。"),
    "adjusted_close": (
        "收盘价（复权）",
        "按复权因子调整后的收盘价，用于处理分红、送转等造成的价格变化。",
    ),
    "pre_close": (
        "前收盘价",
        "前一交易日的收盘参考价；除权除息日是否调整，取决于数据源的字段口径。",
    ),
    "volume": ("成交量", "当日成交的股票数量。"),
    "amount": ("成交额", "当日股票成交的总金额。"),
}


def field_description(field: str) -> tuple[str, str]:
    """Keep unknown field identifiers visible instead of inventing a meaning."""
    return FIELD_DESCRIPTIONS.get(field, (field, "暂无字段说明，请查阅该因子或数据源的定义。"))
