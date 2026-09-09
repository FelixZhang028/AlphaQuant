"""Common China-market benchmark display names and symbols."""

BENCHMARKS = {
    "沪深 300": "000300.SH",
    "中证 500": "000905.SH",
    "中证 1000": "000852.SH",
    "中证 2000": "932000.CSI",
    "创业板指": "399006.SZ",
    "科创 50": "000688.SH",
    "中证全指": "000985.SH",
    "上证指数": "000001.SH",
    "深证成指": "399001.SZ",
}

BENCHMARK_NAMES = {symbol: name for name, symbol in BENCHMARKS.items()}
