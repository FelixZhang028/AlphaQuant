"""Second batch: daily VWAP and dollar-volume alphas from Appendix A."""

from functools import partial

import numpy as np

from quant_platform.factors.alpha_operators import correlation as corr
from quant_platform.factors.alpha_operators import divide, finite, rank
from quant_platform.factors.base import melt_wide, pivot_field
from quant_platform.factors.builtins import BuiltinFactor


def scale(x):
    """L1 scale within the available cross section; zero norm stays missing."""
    return finite(x.div(x.abs().sum(axis=1).replace(0, np.nan), axis=0))


def compute(number, bars):
    cache = {}

    def field(name):
        if name not in cache:
            cache[name] = finite(pivot_field(bars, name))
        return cache[name]

    def close():
        return field("raw_close")

    def vwap():
        volume, amount = field("volume"), field("amount")
        return divide(amount.where(amount > 0), volume.where(volume > 0))

    def adv(n=20):
        # Paper A.2 defines average daily dollar volume, not average share volume.
        return field("amount").where(field("amount") >= 0).rolling(n).mean()

    def returns():
        return divide(close(), close().shift()) - 1

    if number == 5:
        w = vwap()
        out = rank(field("raw_open") - w.rolling(10).mean()) * -rank(close() - w).abs()
    elif number == 8:
        x = field("raw_open").rolling(5).sum() * returns().rolling(5).sum()
        out = -rank(x - x.shift(10))
    elif number == 11:
        x = vwap() - close()
        out = (rank(x.rolling(3).max()) + rank(x.rolling(3).min())) * rank(field("volume").diff(3))
    elif number == 19:
        c = close()
        out = -np.sign(c - c.shift(7) + c.diff(7)) * (1 + rank(1 + returns().rolling(250).sum()))
    elif number == 21:
        c = close()
        mean, std, short = c.rolling(8).mean(), c.rolling(8).std(), c.rolling(2).mean()
        ratio = divide(field("volume"), adv())
        out = ratio.ge(1).astype(float) * 2 - 1
        out = out.where(~(short < mean - std), 1).where(~(mean + std < short), -1)
        out = out.where(mean.notna() & std.notna() & short.notna() & ratio.notna())
    elif number == 24:
        c = close()
        mean = c.rolling(100).mean()
        change = divide(mean.diff(100), c.shift(100))
        out = (-(c - c.rolling(100).min())).where(change <= 0.05, -c.diff(3))
        out = out.where(change.notna())
    elif number == 25:
        out = rank(-returns() * adv() * vwap() * (field("raw_high") - close()))
    elif number == 27:
        x = rank(corr(rank(field("volume")), rank(vwap()), 6).rolling(2).mean())
        out = (1 - 2 * x.gt(0.5).astype(float)).where(x.notna())
    elif number == 28:
        low = field("raw_low")
        out = scale(corr(adv(), low, 5) + (field("raw_high") + low) / 2 - close())
    elif number == 30:
        c, volume = close(), field("volume")
        signs = np.sign(c.diff()) + np.sign(c.shift().diff()) + np.sign(c.shift(2).diff())
        out = divide((1 - rank(signs)) * volume.rolling(5).sum(), volume.rolling(20).sum())
    elif number == 32:
        c = close()
        out = scale(c.rolling(7).mean() - c) + 20 * scale(corr(vwap(), c.shift(5), 230))
    elif number == 37:
        x = field("raw_open") - close()
        out = rank(corr(x.shift(), close(), 200)) + rank(x)
    elif number == 41:
        product = field("raw_high") * field("raw_low")
        out = np.sqrt(product.where(product >= 0)) - vwap()
    elif number == 42:
        out = divide(rank(vwap() - close()), rank(vwap() + close()))
    elif number == 45:
        c = close()
        out = -rank(c.shift(5).rolling(20).mean()) * corr(c, field("volume"), 2)
        out *= rank(corr(c.rolling(5).sum(), c.rolling(20).sum(), 2))
    elif number in {46, 49, 51}:
        c = close()
        slope = (c.shift(20) - c.shift(10)) / 10 - (c.shift(10) - c) / 10
        threshold = {46: 0, 49: -0.1, 51: -0.05}[number]
        out = (-c.diff()).where(~(slope < threshold), 1)
        if number == 46:
            out = out.where(~(slope > 0.25), -1)
        out = out.where(slope.notna() & c.diff().notna())
    elif number == 47:
        c, high = close(), field("raw_high")
        out = divide(rank(divide(c * 0 + 1, c)) * field("volume"), adv())
        out *= divide(high * rank(high - c), high.rolling(5).mean())
        out -= rank(vwap().diff(5))
    elif number == 50:
        out = -rank(corr(rank(field("volume")), rank(vwap()), 5)).rolling(5).max()
    else:
        raise ValueError(f"Unknown batch-two alpha: {number}")
    return melt_wide(finite(out))


# Data symbols below expand to canonical raw fields; VWAP is never OHLC averaging.
FIELDS = dict(o="raw_open", c="raw_close", h="raw_high", l="raw_low", v="volume", a="amount")
DEFINITIONS = [
    (
        5,
        "开盘偏离均价与收盘偏离排名",
        10,
        "ocva",
        "rank(open - mean(vwap, 10)) * -abs(rank(close - vwap))",
    ),
    (8, "开盘价与收益累积变化排名", 16, "oc", "-rank(delta(sum(open, 5) * sum(returns, 5), 10))"),
    (
        11,
        "均价收盘偏离与成交量变化",
        4,
        "cva",
        "(rank(ts_max(vwap-close, 3)) + rank(ts_min(vwap-close, 3))) * rank(delta(volume, 3))",
    ),
    (
        19,
        "短期价格方向与长期收益排名",
        251,
        "c",
        "-sign(close-delay(close, 7)+delta(close, 7)) * (1+rank(1+sum(returns, 250)))",
    ),
    (
        21,
        "均线波动区间与成交条件信号",
        20,
        "cva",
        "mean(close,8)+stddev(close,8)<mean(close,2) ? -1 : "
        "(mean(close,2)<mean(close,8)-stddev(close,8) ? 1 : (volume/adv20>=1 ? 1 : -1))",
    ),
    (
        24,
        "长期均线变化条件反转",
        200,
        "c",
        "delta(mean(close,100),100)/delay(close,100)<=0.05 ? "
        "-(close-ts_min(close,100)) : -delta(close,3)",
    ),
    (25, "收益成交额均价与高价偏离", 20, "chva", "rank(-returns * adv20 * vwap * (high-close))"),
    (
        27,
        "成交量均价排名相关条件信号",
        7,
        "va",
        "rank(mean(correlation(rank(volume),rank(vwap),6),2))>0.5 ? -1 : 1",
    ),
    (
        28,
        "成交额低价相关与价格位置",
        24,
        "chla",
        "scale(correlation(adv20,low,5)+(high+low)/2-close)",
    ),
    (
        30,
        "连续涨跌方向与成交量占比",
        20,
        "cv",
        "(1-rank(sign(delta(close,1))+sign(delta(delay(close,1),1))+"
        "sign(delta(delay(close,2),1)))) * sum(volume,5)/sum(volume,20)",
    ),
    (
        32,
        "均线偏离与长期均价相关",
        235,
        "cva",
        "scale(mean(close,7)-close)+20*scale(correlation(vwap,delay(close,5),230))",
    ),
    (
        37,
        "滞后开收盘差与收盘相关排名",
        201,
        "oc",
        "rank(correlation(delay(open-close,1),close,200))+rank(open-close)",
    ),
    (41, "高低价几何均值与成交均价差", 1, "hlva", "sqrt(high*low)-vwap"),
    (42, "均价收盘价差与价格和排名比", 1, "cva", "rank(vwap-close)/rank(vwap+close)"),
    (
        45,
        "滞后均价与多窗口量价相关",
        25,
        "cv",
        "-rank(mean(delay(close,5),20))*correlation(close,volume,2)*rank(correlation(sum(close,5),sum(close,20),2))",
    ),
    (
        46,
        "价格斜率变化分段反转",
        21,
        "c",
        "slope=(delay(close,20)-delay(close,10))/10-(delay(close,10)-close)/10; "
        "slope>0.25 ? -1 : (slope<0 ? 1 : -delta(close,1))",
    ),
    (
        47,
        "低价排名量价组合与均价变化",
        20,
        "chva",
        "rank(1/close)*volume/adv20 * (high*rank(high-close)/mean(high,5)) - rank(delta(vwap,5))",
    ),
    (
        49,
        "价格斜率负阈值反转",
        21,
        "c",
        "((delay(close,20)-delay(close,10))/10-(delay(close,10)-close)/10)<-0.1 "
        "? 1 : -delta(close,1)",
    ),
    (
        50,
        "成交量与均价排名相关峰值",
        9,
        "va",
        "-ts_max(rank(correlation(rank(volume),rank(vwap),5)),5)",
    ),
    (
        51,
        "价格斜率温和负阈值反转",
        21,
        "c",
        "((delay(close,20)-delay(close,10))/10-(delay(close,10)-close)/10)<-0.05 "
        "? 1 : -delta(close,1)",
    ),
]


def batch2_factors():
    return [
        BuiltinFactor(
            name=f"alpha101_{n:03d}",
            display_name=title,
            description=(
                f"{title}。按公式符号输出；A股有效性需独立评估。"
                + ("VWAP=成交额（元）/成交量（股）；adv为平均成交额。" if "a" in fields else "")
                + ("原文为当日收盘执行，本平台次日执行，属于执行时点适配。" if n == 42 else "")
            ),
            formula=formula,
            required_fields=tuple(FIELDS[x] for x in fields),
            min_history=history,
            category="量价",
            source="Alpha101",
            source_url="https://arxiv.org/abs/1601.00991",
            func=partial(compute, n),
        )
        for n, title, history, fields, formula in DEFINITIONS
    ]
