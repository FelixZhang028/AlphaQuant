"""Batch three: rolling ranks, decay weights and nested price-volume signals."""

from functools import partial

import numpy as np

from quant_platform.factors.alpha101_batch2 import FIELDS, scale
from quant_platform.factors.alpha_operators import (
    correlation as corr,
)
from quant_platform.factors.alpha_operators import (
    decay_linear as decay,
)
from quant_platform.factors.alpha_operators import (
    divide,
    finite,
    rank,
    ts_argmax,
    ts_rank,
    window_days,
)
from quant_platform.factors.base import melt_wide, pivot_field
from quant_platform.factors.builtins import BuiltinFactor


def compute(number, bars):
    cache = {}

    def f(name):
        if name not in cache:
            cache[name] = finite(pivot_field(bars, FIELDS[name]))
        return cache[name]

    def returns():
        return divide(f("c"), f("c").shift()) - 1

    def adv(n=20):
        return f("a").where(f("a") >= 0).rolling(n).mean()

    def vwap():
        return divide(f("a").where(f("a") > 0), f("v").where(f("v") > 0))

    def less(x, y):
        return (x < y).astype(float).where(x.notna() & y.notna())

    if number == 1:
        r = returns()
        std = r.rolling(20).std()
        x = std.where(r < 0, f("c")).where(r.notna() & std.notna())
        out = rank(ts_argmax(x**2, 5)) - 0.5
    elif number == 4:
        out = -ts_rank(rank(f("l")), 9)
    elif number == 7:
        change = f("c").diff(7)
        ranked = ts_rank(change.abs(), 60)
        average = adv()
        out = (-ranked * np.sign(change)).where(average < f("v"), -1)
        out = out.where(ranked.notna() & average.notna() & f("v").notna())
    elif number == 17:
        out = -rank(ts_rank(f("c"), 10)) * rank(f("c").diff().diff())
        out *= rank(ts_rank(divide(f("v"), adv()), 5))
    elif number == 26:
        out = -corr(ts_rank(f("v"), 5), ts_rank(f("h"), 5), 5).rolling(3).max()
    elif number == 31:
        out = rank(rank(rank(decay(-rank(rank(f("c").diff(10))), 10))))
        out += rank(-f("c").diff(3)) + np.sign(scale(corr(adv(), f("l"), 12)))
    elif number == 35:
        out = ts_rank(f("v"), 32) * (1 - ts_rank(f("c") + f("h") - f("l"), 16))
        out *= 1 - ts_rank(returns(), 32)
    elif number == 36:
        c, o, v = f("c"), f("o"), f("v")
        out = 2.21 * rank(corr(c - o, v.shift(), 15)) + 0.7 * rank(o - c)
        out += 0.73 * rank(ts_rank((-returns()).shift(6), 5))
        out += rank(corr(vwap(), adv(), 6).abs())
        out += 0.6 * rank((c.rolling(200).mean() - o) * (c - o))
    elif number == 38:
        out = -rank(ts_rank(f("c"), 10)) * rank(divide(f("c"), f("o")))
    elif number == 39:
        out = -rank(f("c").diff(7) * (1 - rank(decay(divide(f("v"), adv()), 9))))
        out *= 1 + rank(returns().rolling(250).sum())
    elif number == 43:
        out = ts_rank(divide(f("v"), adv()), 20) * ts_rank(-f("c").diff(7), 8)
    elif number == 52:
        low = f("l").rolling(5).min()
        r = returns()
        out = (-low + low.shift(5)) * rank((r.rolling(240).sum() - r.rolling(20).sum()) / 220)
        out *= ts_rank(f("v"), 5)
    elif number == 53:
        out = -divide((f("c") - f("l")) - (f("h") - f("c")), f("c") - f("l")).diff(9)
    elif number == 54:
        out = -divide((f("l") - f("c")) * f("o") ** 5, (f("l") - f("h")) * f("c") ** 5)
    elif number == 57:
        out = -divide(f("c") - vwap(), decay(rank(ts_argmax(f("c"), 30)), 2))
    elif number == 60:
        position = divide((f("c") - f("l")) - (f("h") - f("c")), f("h") - f("l"))
        out = -(2 * scale(rank(position * f("v"))) - scale(rank(ts_argmax(f("c"), 10))))
    elif number == 61:
        w = vwap()
        out = less(
            rank(w - w.rolling(window_days(16.1219)).min()),
            rank(corr(w, adv(180), window_days(17.9282))),
        )
    elif number == 64:
        price = f("o") * 0.178404 + f("l") * (1 - 0.178404)
        left = rank(
            corr(
                price.rolling(window_days(12.7054)).sum(),
                adv(120).rolling(window_days(12.7054)).sum(),
                window_days(16.6208),
            )
        )
        right = rank(
            ((f("h") + f("l")) / 2 * 0.178404 + vwap() * (1 - 0.178404)).diff(window_days(3.69741))
        )
        out = -less(left, right)
    elif number == 65:
        left = rank(
            corr(
                f("o") * 0.00817205 + vwap() * (1 - 0.00817205),
                adv(60).rolling(window_days(8.6911)).sum(),
                window_days(6.40374),
            )
        )
        right = rank(f("o") - f("o").rolling(window_days(13.635)).min())
        out = -less(left, right)
    elif number == 75:
        out = less(
            rank(corr(vwap(), f("v"), window_days(4.24304))),
            rank(corr(rank(f("l")), rank(adv(50)), window_days(12.4413))),
        )
    else:
        raise ValueError(f"Unknown batch-three alpha: {number}")
    return melt_wide(finite(out))


DEFINITIONS = [
    (
        1,
        "下跌波动与价格极值位置排名",
        25,
        "c",
        "rank(ts_argmax((returns<0 ? stddev(returns,20) : close)^2,5))-0.5",
    ),
    (4, "最低价截面排名的时序反转", 9, "l", "-ts_rank(rank(low),9)"),
    (
        7,
        "成交条件下的价格变化排名",
        67,
        "cva",
        "adv20<volume ? -ts_rank(abs(delta(close,7)),60)*sign(delta(close,7)) : -1",
    ),
    (
        17,
        "价格排名加速度与成交比排名",
        24,
        "cva",
        "-rank(ts_rank(close,10))*rank(delta(delta(close,1),1))*rank(ts_rank(volume/adv20,5))",
    ),
    (
        26,
        "成交量与高价时序排名相关峰值",
        11,
        "vh",
        "-ts_max(correlation(ts_rank(volume,5),ts_rank(high,5),5),3)",
    ),
    (
        31,
        "衰减价格反转与成交额低价相关",
        31,
        "cla",
        "rank(rank(rank(decay_linear(-rank(rank(delta(close,10))),10)))) "
        "+ rank(-delta(close,3)) + sign(scale(correlation(adv20,low,12)))",
    ),
    (
        35,
        "成交量价格位置与收益时序排名",
        33,
        "cvhl",
        "ts_rank(volume,32)*(1-ts_rank(close+high-low,16))*(1-ts_rank(returns,32))",
    ),
    (
        36,
        "多窗口日内价差与量价复合",
        200,
        "ocva",
        "2.21*rank(correlation(close-open,delay(volume,1),15)) + 0.7*rank(open-close) "
        "+ 0.73*rank(ts_rank(delay(-returns,6),5)) + rank(abs(correlation(vwap,adv20,6))) "
        "+ 0.6*rank((mean(close,200)-open)*(close-open))",
    ),
    (38, "收盘时序排名与开收盘比", 10, "oc", "-rank(ts_rank(close,10))*rank(close/open)"),
    (
        39,
        "成交比衰减反转与长期收益",
        251,
        "cva",
        "-rank(delta(close,7)*(1-rank(decay_linear(volume/adv20,9))))*(1+rank(sum(returns,250)))",
    ),
    (
        43,
        "成交比与反向价格变化时序排名",
        39,
        "cva",
        "ts_rank(volume/adv20,20)*ts_rank(-delta(close,7),8)",
    ),
    (
        52,
        "低价变化与长期收益成交排名",
        241,
        "clv",
        "(-ts_min(low,5)+delay(ts_min(low,5),5))*rank((sum(returns,240)-sum(returns,20))/220)*ts_rank(volume,5)",
    ),
    (53, "日内价格位置比例变化", 10, "chl", "-delta(((close-low)-(high-close))/(close-low),9)"),
    (54, "高低价差与开收盘幂次比例", 1, "ochl", "-((low-close)*open^5)/((low-high)*close^5)"),
    (
        57,
        "收盘均价差与极值位置衰减",
        31,
        "cva",
        "-(close-vwap)/decay_linear(rank(ts_argmax(close,30)),2)",
    ),
    (
        60,
        "量价位置与收盘极值排名对比",
        10,
        "chlv",
        "-(2*scale(rank(((close-low)-(high-close))/(high-low)*volume))-scale(rank(ts_argmax(close,10))))",
    ),
    (
        61,
        "均价低点偏离与长期成交额相关",
        196,
        "va",
        "rank(vwap-ts_min(vwap,16.1219))<rank(correlation(vwap,adv180,17.9282))",
    ),
    (
        64,
        "混合价格成交额相关与价格变化",
        146,
        "ohlva",
        "-(rank(correlation(sum(open*0.178404+low*(1-0.178404),12.7054),"
        "sum(adv120,12.7054),16.6208)) "
        "< rank(delta((high+low)/2*0.178404+vwap*(1-0.178404),3.69741)))",
    ),
    (
        65,
        "混合均价成交额相关与开盘位置",
        72,
        "ova",
        "-(rank(correlation(open*0.00817205+vwap*(1-0.00817205),sum(adv60,8.6911),6.40374)) "
        "< rank(open-ts_min(open,13.635)))",
    ),
    (
        75,
        "均价量相关与低价成交额相关对比",
        61,
        "lva",
        "rank(correlation(vwap,volume,4.24304)) < rank(correlation(rank(low),rank(adv50),12.4413))",
    ),
]


def batch3_factors():
    return [
        BuiltinFactor(
            name=f"alpha101_{n:03d}",
            display_name=title,
            description=f"{title}。滚动排名为序数，衰减权重越近越大；A股有效性需独立评估。"
            + ("VWAP=成交额/成交量；adv为平均成交额。" if "a" in fields else "")
            + ("原文为当日收盘执行，本平台次日执行，属于执行时点适配。" if n in {53, 54} else ""),
            formula=formula,
            min_history=history,
            required_fields=tuple(FIELDS[x] for x in fields),
            category="量价",
            source="Alpha101",
            version="1.0.1" if n in {1, 4, 7, 17, 26, 35, 36, 38, 43, 52, 57, 60} else "1.0.0",
            source_url="https://arxiv.org/abs/1601.00991",
            func=partial(compute, n),
        )
        for n, title, history, fields, formula in DEFINITIONS
    ]
