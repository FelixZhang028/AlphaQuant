"""因子系统：统一定义、计算、评估、清洗与组合。

- ``base``：因子定义、FactorContext（防未来数据锚点）与长表约定；
- ``builtins``：仅依赖日频行情的内置量价因子；
- ``custom``：用户在因子研究室定义的自定义因子（结构化参数 + 持久化）；
- ``registry``：因子注册表与全局默认注册表；
- ``evaluation``：IC / 分层收益 / 换手率 / 样本前后段稳定性；
- ``preprocess``：去极值、标准化、缺失值处理、行业中性化；
- ``combine``：多因子加权合成、相关性分析与高相关剔除。
"""

from quant_platform.factors.base import (
    FACTOR_COLUMNS,
    FactorContext,
    FactorDefinition,
    melt_wide,
    pivot_field,
)
from quant_platform.factors.combine import (
    CompositeFactor,
    combine_factors,
    correlation_matrix,
    drop_highly_correlated,
    positive_ic_weights,
)
from quant_platform.factors.custom import (
    CustomFactor,
    build_custom_factor,
    load_custom_factors,
    save_custom_factors,
)
from quant_platform.factors.evaluation import (
    FactorEvaluator,
    FactorReport,
    chronological_train_test_split,
)
from quant_platform.factors.preprocess import (
    FactorPreprocessConfig,
    fill_missing,
    neutralize_industry,
    preprocess_factor,
    preprocess_factor_frames,
    winsorize,
    zscore,
)
from quant_platform.factors.registry import FactorRegistry, default_registry

__all__ = [
    "FACTOR_COLUMNS",
    "CompositeFactor",
    "CustomFactor",
    "FactorContext",
    "FactorDefinition",
    "FactorEvaluator",
    "FactorPreprocessConfig",
    "FactorRegistry",
    "FactorReport",
    "build_custom_factor",
    "combine_factors",
    "chronological_train_test_split",
    "correlation_matrix",
    "default_registry",
    "drop_highly_correlated",
    "fill_missing",
    "load_custom_factors",
    "melt_wide",
    "neutralize_industry",
    "positive_ic_weights",
    "preprocess_factor",
    "preprocess_factor_frames",
    "pivot_field",
    "save_custom_factors",
    "winsorize",
    "zscore",
]
