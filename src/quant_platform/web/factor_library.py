"""Browsable catalog; evaluation and portfolio calculations stay in their tabs."""

import hashlib

import pandas as pd
import streamlit as st

from quant_platform.factors.base import FactorDefinition
from quant_platform.web.factor_fields import field_description

_CATEGORIES = {
    "动量": "动量与趋势",
    "反转": "反转与价格位置",
    "波动": "波动与风险",
    "量价": "K线与量价关系",
    "K线": "K线与量价关系",
    "技术": "反转与价格位置",
}
_OVERRIDES = {
    "amount_change_20": "成交与流动性",
    "volume_ratio_5": "成交与流动性",
    "high_distance_20": "反转与价格位置",
    "bias_10": "反转与价格位置",
    "amplitude_20": "波动与风险",
}


def factor_category(factor: FactorDefinition) -> str:
    if factor.source == "自定义":
        operator = getattr(factor, "operator", "")
        return {
            "momentum": "动量与趋势",
            "bias": "反转与价格位置",
            "sma": "基础行情特征",
            "ma_ratio": "动量与趋势",
            "rolling_std": "波动与风险",
            "volatility": "波动与风险",
            "pv_corr": "K线与量价关系",
        }.get(operator, "未分类")
    return _OVERRIDES.get(factor.name, _CATEGORIES.get(factor.category, factor.category))


_INTENTS = {
    "寻找上涨趋势": {"momentum_20", "high_distance_20"},
    "寻找短期超跌": {"reversal_5", "rsi_14", "bias_10"},
    "偏好低波动": {"volatility_20", "amplitude_20"},
    "关注放量": {"volume_ratio_5", "amount_change_20"},
}
_SYNONYMS = {
    "寻找上涨趋势": "趋势 上涨 涨幅 动量 强势 新高",
    "寻找短期超跌": "超跌 下跌 跌幅 反弹 反转 乖离",
    "偏好低波动": "低波动 波动 振幅 平稳 稳健",
    "关注放量": "放量 成交量 成交额 活跃 流动性",
}


def factor_matches(factor, query):
    terms = " ".join(_SYNONYMS[label] for label, names in _INTENTS.items() if factor.name in names)
    haystack = " ".join(
        [factor.name, factor.display_name, factor.description, factor.formula, terms]
    ).casefold()
    return all(part in haystack for part in query.strip().casefold().split())


def render_factor_library(factors: dict[str, FactorDefinition], *, has_data: bool) -> None:
    st.subheader("因子库")
    st.caption("按投资逻辑找因子，按来源库查公式；选择因子后可继续评估或加入组合。")
    counts = pd.Series([f.source for f in factors.values()]).value_counts()
    st.caption(
        " · ".join(
            f"{source} {count}/101 已接入" if source == "Alpha101" else f"{source} {count} 个"
            for source, count in counts.items()
        )
    )
    intent = st.pills("我想研究", ["全部", *_INTENTS], default="全部", key="library_intent")
    st.caption("意图标签用于寻找研究方向，不代表因子已被证明有效。点击表格行可查看详情。")
    cols = st.columns([2, 1, 1])
    query = cols[0].text_input(
        "搜索因子", placeholder="试试：放量、涨幅、低波动，也支持名称和编号", key="library_search"
    )
    category = cols[1].selectbox(
        "因子类别",
        ["全部"] + sorted({factor_category(f) for f in factors.values()}),
        key="library_category",
    )
    source = cols[2].selectbox(
        "来源库",
        ["全部"] + sorted(counts.index.tolist()),
        key="library_source",
    )
    matching = [
        f
        for f in factors.values()
        if (category == "全部" or factor_category(f) == category)
        and (source == "全部" or f.source == source)
        and (not intent or intent == "全部" or f.name in _INTENTS[intent])
        and factor_matches(f, query)
    ]
    st.caption(
        f"显示 {len(matching)} / {len(factors)} 个因子。评价需指定日期和持有期，不设永久有效标签。"
    )
    if not matching:
        st.session_state.pop("library_open_factor", None)
        st.info("没有匹配的因子，请调整关键词或筛选条件。")
        return
    identity = repr((query, category, source, intent, [(f.name, f.version) for f in matching]))
    if st.session_state.get("library_open_identity") != identity:
        st.session_state.pop("library_open_factor", None)
        st.session_state["library_open_identity"] = identity
    names = [f.name for f in matching]
    selection_key = "library_rows_" + hashlib.sha256(identity.encode()).hexdigest()[:16]
    selection_key += "_" + str(st.session_state.get("library_selection_epoch", 0))

    def remember_selection():
        rows = st.session_state[selection_key]["selection"]["rows"]
        st.session_state["library_open_factor"] = names[rows[0]] if rows else None

    selection = st.dataframe(
        pd.DataFrame(
            [
                {
                    "因子名": f.name,
                    "中文名": f.display_name,
                    "类别": factor_category(f),
                    "来源": f.source,
                    "类型": f.feature_type,
                    "最小历史（条/股票）": f.min_history,
                    "默认方向": "正向" if f.direction == 1 else "反向",
                    "说明": f.description,
                }
                for f in matching
            ]
        ),
        width="stretch",
        hide_index=True,
        on_select=remember_selection,
        selection_mode="single-row",
        key=selection_key,
    )
    rows = selection.selection.rows
    if rows:
        st.session_state["library_open_factor"] = names[rows[0]]
    detail_name = st.session_state.get("library_open_factor")
    if detail_name not in names:
        return
    if st.button("收起详情", key="library_close"):
        st.session_state.pop("library_open_factor", None)
        st.session_state["library_selection_epoch"] = (
            st.session_state.get("library_selection_epoch", 0) + 1
        )
        st.rerun()
    factor = factors[detail_name]
    with st.container(border=True):
        st.markdown(f"**{factor.display_name}**")
        st.write(factor.description)
        st.code(factor.formula, language="text")
        st.caption(
            f"类别：{factor_category(factor)} ｜ 来源：{factor.source} ｜ 日频 ｜ "
            f"最小历史：每只股票 {factor.min_history} 条 ｜ 版本：{factor.version}"
        )
        st.write("所需字段：" + "、".join(field_description(f)[0] for f in factor.required_fields))
        with st.expander("查看字段说明"):
            st.table(
                pd.DataFrame(
                    [
                        {
                            "字段": field,
                            "中文名称": field_description(field)[0],
                            "说明": field_description(field)[1],
                        }
                        for field in factor.required_fields
                    ]
                )
            )
        st.caption("回看窗口由公式定义；最小历史是计算所需数据量，不是回测区间。")
        if factor.source_url:
            st.markdown(f"[公式来源]({factor.source_url})")
            st.caption(
                "本批 Alpha101 使用未复权 OHLC 和原始成交量；公司行动可能影响信号。"
                "rank 为当前输入股票池的截面百分位排名，结果随股票池变化。"
            )
        if not has_data:
            st.info("暂无本地行情。可浏览和选择因子，评估前请先更新数据。")
        else:
            st.caption("数据字段与历史长度将在评估时校验；已有行情不代表每个因子都有足够数据。")
        left, right = st.columns(2)
        if left.button("用于因子评估", key="library_to_eval", type="primary"):
            st.session_state["factor_eval_name"] = detail_name
            st.success("已选入「因子评估」，请切换标签设置日期并开始评估。")
        if right.button("加入因子组合", key="library_to_combine"):
            current = list(st.session_state.get("factor_combine_names", []))
            st.session_state["factor_combine_names"] = list(dict.fromkeys([*current, detail_name]))
            st.success("已加入「因子组合」，请切换标签配置权重。")
