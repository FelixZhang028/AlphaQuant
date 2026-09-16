"""Research catalog metadata, independent of computation and trading direction.

Categories describe the dominant formula structure, not validated economic exposures.
Alpha101 membership is explicitly reviewed; new formulas must be classified separately.
"""

from dataclasses import dataclass

from quant_platform.factors.base import FactorDefinition


@dataclass(frozen=True)
class FactorClassification:
    category: str
    intents: tuple[str, ...]
    rationale: str


INTENT_TERMS = {
    "寻找上涨趋势": "趋势 上涨 涨幅 动量 强势 新高",
    "寻找短期超跌": "超跌 下跌 跌幅 反弹 反转 乖离",
    "偏好低波动": "低波动 平稳 稳健",
    "关注放量": "放量 成交量 成交额 活跃 流动性",
    "研究量价关系": "量价 相关性 协方差 成交量 成交额",
    "研究价格位置": "价格位置 K线 开盘 收盘 高低点 VWAP",
    "研究波动变化": "波动 振幅 标准差",
    "研究复合信号": "复合 混合 条件 分支",
}

# Each implemented Alpha101 belongs to exactly one primary category.
_ALPHA_GROUPS = (
    (
        (2, 3, 6, 13, 15, 16, 26, 27, 44, 50, 55, 72, 74, 75, 78, 81, 85, 96, 98, 99),
        "量价关系",
        ("研究量价关系",),
        "以价格与成交量或成交额的相关、协方差及其排序为主要结构；不直接表示放量看涨。",
    ),
    (
        (4, 5, 19, 23, 24, 30, 33, 38, 39, 42, 43, 57),
        "反转与偏离",
        ("寻找短期超跌", "研究价格位置"),
        "含负向价格变化、相对价格排名或均价偏离，可用于研究反转；不等同于超跌买入条件。",
    ),
    (
        (20, 41, 53, 54, 101),
        "K线与价格位置",
        ("研究价格位置",),
        "主要比较开高低收、前日价格或成交均价之间的位置与形态。",
    ),
    (
        (1, 18, 22, 34, 40),
        "复合信号",
        ("研究复合信号", "研究波动变化"),
        "将波动统计与价格或量价关系结合，整体信号不等于低波动排序。",
    ),
    (
        (
            7,
            11,
            12,
            14,
            17,
            21,
            25,
            28,
            31,
            35,
            36,
            45,
            47,
            52,
            60,
            61,
            62,
            64,
            65,
            68,
            71,
            77,
            83,
            86,
            88,
            92,
            94,
            95,
        ),
        "复合信号",
        ("研究复合信号", "研究量价关系"),
        "价格变化或位置与成交信息通过乘积、比较、条件或多项组合形成信号，需联合评估。",
    ),
    (
        (8, 9, 10, 29, 32, 37, 46, 49, 51, 66, 73, 84),
        "复合信号",
        ("研究复合信号", "研究价格位置"),
        "组合多个价格变化、位置或时序关系，或随条件切换方向，不宜直接归为单一趋势信号。",
    ),
)
ALPHA_CLASSIFICATIONS: dict[str, FactorClassification] = {}
for _numbers, _category, _intents, _rationale in _ALPHA_GROUPS:
    for _number in _numbers:
        _name = f"alpha101_{_number:03d}"
        if _name in ALPHA_CLASSIFICATIONS:
            raise ValueError(f"重复分类：{_name}")
        ALPHA_CLASSIFICATIONS[_name] = FactorClassification(_category, _intents, _rationale)

_BUILTINS = {
    "momentum_20": ("动量与趋势", ("寻找上涨趋势",)),
    "high_distance_20": ("K线与价格位置", ("寻找上涨趋势", "研究价格位置")),
    "reversal_5": ("反转与偏离", ("寻找短期超跌",)),
    "rsi_14": ("反转与偏离", ("寻找短期超跌",)),
    "bias_10": ("反转与偏离", ("寻找短期超跌", "研究价格位置")),
    "volatility_20": ("波动与风险", ("偏好低波动", "研究波动变化")),
    "amplitude_20": ("波动与风险", ("偏好低波动", "研究波动变化")),
    "volume_ratio_5": ("成交与流动性", ("关注放量",)),
    "amount_change_20": ("成交与流动性", ("关注放量",)),
    "pv_corr_20": ("量价关系", ("研究量价关系",)),
}
_OPERATORS = {
    "momentum": ("动量与趋势", ("寻找上涨趋势",)),
    "ma_ratio": ("动量与趋势", ("寻找上涨趋势",)),
    "bias": ("反转与偏离", ("研究价格位置",)),
    "sma": ("基础行情特征", ("研究价格位置",)),
    "rolling_std": ("波动与风险", ("研究波动变化",)),
    "volatility": ("波动与风险", ("研究波动变化",)),
    "pv_corr": ("量价关系", ("研究量价关系",)),
}


def classify_factor(factor: FactorDefinition) -> FactorClassification:
    """Custom factors cannot inherit labels just by reusing a built-in name."""
    if factor.source == "自定义":
        category, intents = _OPERATORS.get(getattr(factor, "operator", ""), ("未分类", ()))
        return FactorClassification(
            category, intents, "按自定义算子归类；请结合输入字段和方向核对含义。"
        )
    if factor.source == "Alpha101":
        return ALPHA_CLASSIFICATIONS.get(
            factor.name, FactorClassification("未分类", (), "尚未审核此公式的研究分类。")
        )
    if factor.source == "内置" and factor.name in _BUILTINS:
        category, intents = _BUILTINS[factor.name]
        return FactorClassification(
            category, intents, "按内置公式的主要研究用途归类；有效性需另行评估。"
        )
    return FactorClassification(factor.category, (), "暂无经过审核的研究意图标签。")


def factor_category(factor: FactorDefinition) -> str:
    return classify_factor(factor).category


def factor_intents(factor: FactorDefinition) -> tuple[str, ...]:
    return classify_factor(factor).intents
