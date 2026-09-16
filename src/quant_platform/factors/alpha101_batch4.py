"""Final price-volume batch from the Alpha101 appendix (no industry inputs)."""

from functools import partial

import numpy as np
import pandas as pd

from quant_platform.factors.alpha101_batch2 import FIELDS, scale
from quant_platform.factors.alpha_operators import (
    decay_linear as decay,
)
from quant_platform.factors.alpha_operators import (
    divide,
    finite,
    rank,
    ts_argmax,
    ts_argmin,
)
from quant_platform.factors.alpha_operators import (
    ts_rank as tr,
)
from quant_platform.factors.alpha_operators import (
    window_days as days,
)
from quant_platform.factors.base import melt_wide, pivot_field
from quant_platform.factors.builtins import BuiltinFactor


def compute(number, bars):
    cache = {}

    def f(name):
        if name not in cache:
            cache[name] = finite(pivot_field(bars, FIELDS[name]))
        return cache[name]

    def adv(n):
        return f("a").where(f("a") >= 0).rolling(days(n)).mean()

    def w():
        return divide(f("a").where(f("a") > 0), f("v").where(f("v") > 0))

    def total(x, n):
        return x.rolling(days(n)).sum()

    def delta(x, n):
        return x.diff(days(n))

    def corr(x, y, n):
        # Center full windows before multiplying: rolling raw moments can turn
        # equal rank correlations into different ranks through cancellation.
        n = days(n)
        out = np.full(x.shape, np.nan)
        if len(x) >= n:
            xx = np.lib.stride_tricks.sliding_window_view(x.to_numpy(), n, axis=0)
            yy = np.lib.stride_tricks.sliding_window_view(y.to_numpy(), n, axis=0)
            valid = np.isfinite(xx).all(axis=-1) & np.isfinite(yy).all(axis=-1)
            valid &= (np.ptp(xx, axis=-1) > 0) & (np.ptp(yy, axis=-1) > 0)
            xx = xx - xx.mean(axis=-1, keepdims=True)
            yy = yy - yy.mean(axis=-1, keepdims=True)
            denominator = np.sqrt((xx**2).sum(axis=-1) * (yy**2).sum(axis=-1))
            out[n - 1 :] = np.divide(
                (xx * yy).sum(axis=-1),
                denominator,
                out=np.full(denominator.shape, np.nan),
                where=valid & (denominator > 0),
            )
        return pd.DataFrame(out, index=x.index, columns=x.columns).clip(-1, 1)

    def less(x, y):
        return (x < y).astype(float).where(x.notna() & y.notna())

    def log(x):
        return np.log(x.where(x > 0))

    def power(x, y):
        # pandas/NumPy define 1**NaN as 1; missing exponents are unavailable signals.
        return finite(x**y).where(x.notna() & y.notna())

    if number == 29:
        x = rank(rank(-rank(delta(f("c") - 1, 5)))).rolling(2).min()
        x = rank(rank(scale(log(total(x, 1)))))
        x = x.rolling(1).apply(np.prod, raw=True).rolling(5).min()
        returns = divide(f("c"), f("c").shift()) - 1
        out = x + tr((-returns).shift(6), 5)
    elif number == 62:
        left = rank(corr(w(), total(adv(20), 22.4101), 9.91009))
        right = rank(less(rank(f("o")) + rank(f("o")), rank((f("h") + f("l")) / 2) + rank(f("h"))))
        out = -less(left, right)
    elif number == 66:
        ratio = divide(
            f("l") * 0.96633 + f("l") * (1 - 0.96633) - w(), f("o") - (f("h") + f("l")) / 2
        )
        out = -(rank(decay(delta(w(), 3.51013), 7.23052)) + tr(decay(ratio, 11.4157), 6.72611))
    elif number == 68:
        left = tr(corr(rank(f("h")), rank(adv(15)), 8.91644), 13.9333)
        right = rank(delta(f("c") * 0.518371 + f("l") * (1 - 0.518371), 1.06157))
        out = -less(left, right)
    elif number == 71:
        left = tr(
            decay(corr(tr(f("c"), 3.43976), tr(adv(180), 12.0647), 18.0175), 4.20501), 15.6948
        )
        right = tr(decay(rank(f("l") + f("o") - 2 * w()) ** 2, 16.4662), 4.4388)
        out = np.maximum(left, right)
    elif number == 72:
        left = rank(decay(corr((f("h") + f("l")) / 2, adv(40), 8.93345), 10.1519))
        right = rank(decay(corr(tr(w(), 3.72469), tr(f("v"), 18.5188), 6.86671), 2.95011))
        out = divide(left, right)
    elif number == 73:
        price = f("o") * 0.147155 + f("l") * (1 - 0.147155)
        left = rank(decay(delta(w(), 4.72775), 2.91864))
        right = tr(decay(-divide(delta(price, 2.03608), price), 3.33829), 16.7411)
        out = -np.maximum(left, right)
    elif number == 74:
        left = rank(corr(f("c"), total(adv(30), 37.4843), 15.1365))
        right = rank(corr(rank(f("h") * 0.0261661 + w() * (1 - 0.0261661)), rank(f("v")), 11.4791))
        out = -less(left, right)
    elif number == 77:
        left = rank(decay(((f("h") + f("l")) / 2 + f("h")) - (w() + f("h")), 20.0451))
        right = rank(decay(corr((f("h") + f("l")) / 2, adv(40), 3.1614), 5.64125))
        out = np.minimum(left, right)
    elif number == 78:
        left = rank(
            corr(
                total(f("l") * 0.352233 + w() * (1 - 0.352233), 19.7428),
                total(adv(40), 19.7428),
                6.83313,
            )
        )
        right = rank(corr(rank(w()), rank(f("v")), 5.77492))
        out = power(left, right)
    elif number == 81:
        x = rank(rank(corr(w(), total(adv(10), 49.6054), 8.47743)) ** 4)
        left = rank(log(x.rolling(days(14.9655)).apply(np.prod, raw=True)))
        right = rank(corr(rank(w()), rank(f("v")), 5.07914))
        out = -less(left, right)
    elif number == 83:
        ratio = divide(f("h") - f("l"), f("c").rolling(5).mean())
        difference = (w() - f("c")).mask(np.isclose(w(), f("c"), rtol=1e-12, atol=0), 0)
        out = divide(rank(ratio.shift(2)) * rank(rank(f("v"))), divide(ratio, difference))
    elif number == 84:
        base = tr(w() - w().rolling(days(15.3217)).max(), 20.7127)
        # The base is a positive ordinal rank, so SignedPower is ordinary power.
        out = power(base, delta(f("c"), 4.96796))
    elif number == 85:
        left = rank(corr(f("h") * 0.876703 + f("c") * (1 - 0.876703), adv(30), 9.61331))
        right = rank(corr(tr((f("h") + f("l")) / 2, 3.70596), tr(f("v"), 10.1595), 7.11408))
        out = power(left, right)
    elif number == 86:
        left = tr(corr(f("c"), total(adv(20), 14.7444), 6.00049), 20.4195)
        right = rank((f("o") + f("c")) - (w() + f("o")))
        out = -less(left, right)
    elif number == 88:
        left = rank(decay(rank(f("o")) + rank(f("l")) - rank(f("h")) - rank(f("c")), 8.06882))
        right = tr(
            decay(corr(tr(f("c"), 8.44728), tr(adv(60), 20.6966), 8.01266), 6.65053), 2.61957
        )
        out = np.minimum(left, right)
    elif number == 92:
        left = tr(decay(less((f("h") + f("l")) / 2 + f("c"), f("l") + f("o")), 14.7221), 18.8683)
        right = tr(decay(corr(rank(f("l")), rank(adv(30)), 7.58555), 6.94024), 6.80584)
        out = np.minimum(left, right)
    elif number == 94:
        left = rank(w() - w().rolling(days(11.5783)).min())
        right = tr(corr(tr(w(), 19.6462), tr(adv(60), 4.02992), 18.0926), 2.70756)
        out = -power(left, right)
    elif number == 95:
        left = rank(f("o") - f("o").rolling(days(12.4105)).min())
        right = tr(
            rank(corr(total((f("h") + f("l")) / 2, 19.1351), total(adv(40), 19.1351), 12.8742))
            ** 5,
            11.7584,
        )
        out = less(left, right)
    elif number == 96:
        left = tr(decay(corr(rank(w()), rank(f("v")), 3.83878), 4.16783), 8.38151)
        x = corr(tr(f("c"), 7.45404), tr(adv(60), 4.13242), 3.65459)
        right = tr(decay(ts_argmax(x, 12.6556), 14.0365), 13.4143)
        out = -np.maximum(left, right)
    elif number == 98:
        left = rank(decay(corr(w(), total(adv(5), 26.4719), 4.58418), 7.18088))
        x = ts_argmin(corr(rank(f("o")), rank(adv(15)), 20.8187), 8.62571)
        right = rank(decay(tr(x, 6.95668), 8.07206))
        out = left - right
    elif number == 99:
        left = rank(corr(total((f("h") + f("l")) / 2, 19.8975), total(adv(60), 19.8975), 8.8136))
        right = rank(corr(f("l"), f("v"), 6.28259))
        out = -less(left, right)
    else:
        raise ValueError(f"Unknown batch-four alpha: {number}")
    return melt_wide(finite(out))


DEFINITIONS = [
    (
        29,
        "嵌套价格反转与滞后收益排名",
        12,
        "c",
        "ts_min(product(rank(rank(scale(log(sum(ts_min(rank(rank(-rank(delta(close-1,5)))),2),1))))),1),5)"
        " + ts_rank(delay(-returns,6),5)",
    ),
    (
        62,
        "均价成交额相关与开盘位置比较",
        49,
        "ohlva",
        "-(rank(correlation(vwap,sum(adv20,22.4101),9.91009)) "
        "< rank(rank(open)+rank(open)<rank((high+low)/2)+rank(high)))",
    ),
    (
        66,
        "均价变化衰减与低价偏离排名",
        16,
        "ohlva",
        "-(rank(decay_linear(delta(vwap,3.51013),7.23052))+ts_rank(decay_linear((low*0.96633+low*(1-0.96633)-vwap)/(open-(high+low)/2),11.4157),6.72611))",
    ),
    (
        68,
        "高价成交额相关排名与价格变化",
        34,
        "chla",
        "-(ts_rank(correlation(rank(high),rank(adv15),8.91644),13.9333)<rank(delta(close*0.518371+low*(1-0.518371),1.06157)))",
    ),
    (
        71,
        "长期量价排名相关与均价偏离",
        225,
        "oclva",
        "max(ts_rank(decay_linear(correlation(ts_rank(close,3.43976),ts_rank(adv180,12.0647),18.0175),4.20501),15.6948),ts_rank(decay_linear(rank(low+open-2*vwap)^2,16.4662),4.4388))",
    ),
    (
        72,
        "中间价成交额与均价成交量相关比",
        56,
        "hlva",
        "rank(decay_linear(correlation((high+low)/2,adv40,8.93345),10.1519))/rank(decay_linear(correlation(ts_rank(vwap,3.72469),ts_rank(volume,18.5188),6.86671),2.95011))",
    ),
    (
        73,
        "均价变化与混合价格变化衰减",
        20,
        "olva",
        "-max(rank(decay_linear(delta(vwap,4.72775),2.91864)),ts_rank(decay_linear(-delta(open*0.147155+low*(1-0.147155),2.03608)/(open*0.147155+low*(1-0.147155)),3.33829),16.7411))",
    ),
    (
        74,
        "收盘成交额相关与高价均价相关",
        80,
        "chva",
        "-(rank(correlation(close,sum(adv30,37.4843),15.1365))<rank(correlation(rank(high*0.0261661+vwap*(1-0.0261661)),rank(volume),11.4791)))",
    ),
    (
        77,
        "中间价均价偏离与成交额相关衰减",
        46,
        "hlva",
        "min(rank(decay_linear((high+low)/2+high-(vwap+high),20.0451)),rank(decay_linear(correlation((high+low)/2,adv40,3.1614),5.64125)))",
    ),
    (
        78,
        "混合低价成交额与均价量相关幂",
        63,
        "lva",
        "rank(correlation(sum(low*0.352233+vwap*(1-0.352233),19.7428),sum(adv40,19.7428),6.83313))^rank(correlation(rank(vwap),rank(volume),5.77492))",
    ),
    (
        81,
        "均价成交额相关乘积与量价相关",
        78,
        "va",
        "-(rank(log(product(rank(rank(correlation(vwap,sum(adv10,49.6054),8.47743))^4),14.9655)))<rank(correlation(rank(vwap),rank(volume),5.07914)))",
    ),
    (
        83,
        "振幅比例与均价收盘偏离",
        7,
        "chlva",
        "rank(delay((high-low)/mean(close,5),2))*rank(rank(volume))/(((high-low)/mean(close,5))/(vwap-close))",
    ),
    (
        84,
        "均价高点偏离排名的价格变化幂",
        34,
        "cva",
        "SignedPower(ts_rank(vwap-ts_max(vwap,15.3217),20.7127),delta(close,4.96796))",
    ),
    (
        85,
        "混合高价成交额与时序量价相关幂",
        38,
        "chlva",
        "rank(correlation(high*0.876703+close*(1-0.876703),adv30,9.61331))^rank(correlation(ts_rank((high+low)/2,3.70596),ts_rank(volume,10.1595),7.11408))",
    ),
    (
        86,
        "收盘成交额相关排名与均价差",
        57,
        "ocva",
        "-(ts_rank(correlation(close,sum(adv20,14.7444),6.00049),20.4195)<rank(open+close-(vwap+open)))",
    ),
    (
        88,
        "价格截面排名衰减与量价时序相关",
        92,
        "ochla",
        "min(rank(decay_linear(rank(open)+rank(low)-rank(high)-rank(close),8.06882)),ts_rank(decay_linear(correlation(ts_rank(close,8.44728),ts_rank(adv60,20.6966),8.01266),6.65053),2.61957))",
    ),
    (
        92,
        "日内价格条件与低价成交额衰减",
        46,
        "ochla",
        "min(ts_rank(decay_linear((high+low)/2+close<low+open,14.7221),18.8683),ts_rank(decay_linear(correlation(rank(low),rank(adv30),7.58555),6.94024),6.80584))",
    ),
    (
        94,
        "均价低点偏离与时序成交额相关幂",
        81,
        "va",
        "-rank(vwap-ts_min(vwap,11.5783))^ts_rank(correlation(ts_rank(vwap,19.6462),ts_rank(adv60,4.02992),18.0926),2.70756)",
    ),
    (
        95,
        "开盘低点偏离与量价相关时序排名",
        79,
        "ohla",
        "rank(open-ts_min(open,12.4105))<ts_rank(rank(correlation(sum((high+low)/2,19.1351),sum(adv40,19.1351),12.8742))^5,11.7584)",
    ),
    (
        96,
        "均价量相关与量价相关极值衰减",
        101,
        "cva",
        "-max(ts_rank(decay_linear(correlation(rank(vwap),rank(volume),3.83878),4.16783),8.38151),ts_rank(decay_linear(ts_argmax(correlation(ts_rank(close,7.45404),ts_rank(adv60,4.13242),3.65459),12.6556),14.0365),13.4143))",
    ),
    (
        98,
        "均价成交额相关与开盘相关谷值",
        53,
        "ova",
        "rank(decay_linear(correlation(vwap,sum(adv5,26.4719),4.58418),7.18088))-rank(decay_linear(ts_rank(ts_argmin(correlation(rank(open),rank(adv15),20.8187),8.62571),6.95668),8.07206))",
    ),
    (
        99,
        "累积中间价成交额相关与低价量相关",
        85,
        "hlva",
        "-(rank(correlation(sum((high+low)/2,19.8975),sum(adv60,19.8975),8.8136))<rank(correlation(low,volume,6.28259)))",
    ),
]


def batch4_factors():
    return [
        BuiltinFactor(
            name=f"alpha101_{n:03d}",
            display_name=title,
            formula=formula,
            description=f"{title}。小数窗口向下取整，缺失输入不生成默认信号；A股有效性需独立评估。"
            + ("VWAP=成交额/成交量，adv为平均成交额。" if "a" in fields else ""),
            min_history=history,
            required_fields=tuple(FIELDS[x] for x in fields),
            category="量价",
            source="Alpha101",
            source_url="https://arxiv.org/abs/1601.00991",
            func=partial(compute, n),
        )
        for n, title, history, fields, formula in DEFINITIONS
    ]
