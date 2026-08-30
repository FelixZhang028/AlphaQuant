"""策略创作中心：把模板、积木、自然语言和 Python 四种创建方式整合为一个入口。

对应反馈第 2、3 条：按「入门 / 普通 / 高级」三个等级组织创建入口，
三种方式最终都汇入同一套策略注册、回测与版本管理流程：
模板 / 积木 / 自然语言 -> StrategyPackageStore（JSON 策略包）；
Python 自定义 -> user_strategies 注册表（带安全检查）。
"""

from __future__ import annotations

import streamlit as st

from quant_platform.application.backtest_service import BacktestService
from quant_platform.application.strategy_studio_service import StrategyStudioService
from quant_platform.web.theme import inject_global_css

inject_global_css()

st.title("策略创作中心")
st.caption(
    "四种方式创建策略，共用同一套注册、回测与版本管理流程。"
    "不确定选哪种？入门用户建议从模板开始。"
)

level_tabs = st.tabs(["🌱 入门：策略模板", "🧩 普通：积木组合", "💬 自然语言", "🐍 高级：Python"])

with level_tabs[0]:
    st.subheader("选择现成模板")
    st.markdown(
        "从 6 个内置模板中选一个，再选保守 / 均衡 / 激进风格即可生成策略，"
        "无需任何编程。"
    )
    st.markdown("- 适合：第一次使用平台、想快速看到回测结果")
    st.markdown("- 产出：可在「零代码策略工作台 → 已保存策略」中复用和回测")
    if st.button("打开模板库", key="hub_goto_template", type="primary"):
        st.switch_page("pages/7_strategy_studio.py")

with level_tabs[1]:
    st.subheader("积木组合条件")
    st.markdown(
        "用白名单指标（均线、涨跌幅、成交额、RSI 等）自由组合买入条件与排序规则，"
        "平台自动生成参数表单。"
    )
    st.markdown("- 适合：有自己的交易想法，但不想写代码")
    st.markdown("- 产出：与模板相同的 JSON 策略包，可走完全相同的回测流程")
    if st.button("打开积木编辑器", key="hub_goto_builder", type="primary"):
        st.switch_page("pages/7_strategy_studio.py")

with level_tabs[2]:
    st.subheader("自然语言创建")
    st.markdown(
        "用一句话描述策略，例如「5日均线高于20日均线并且放量时买入」，"
        "大模型先转换成结构化规则并展示中文解释，确认无误后再生成策略。"
    )
    st.markdown("- 适合：能清楚描述想法，希望 AI 帮忙落成规则")
    st.markdown("- 支持 DeepSeek / Kimi 等云端 API 与 Ollama 本地模型；"
                "未配置模型时请改用模板或积木编辑器")
    if st.button("打开自然语言建策略", key="hub_goto_nl", type="primary"):
        st.switch_page("pages/10_nl_strategy.py")

with level_tabs[3]:
    st.subheader("编写或上传 Python")
    st.markdown(
        "在网页中编写完整的 Python 策略类，注册前自动进行安全检查"
        "（未来函数、禁用模块、参数关系等），严重问题会直接阻止保存。"
    )
    st.markdown("- 适合：需要完全自定义逻辑的高级用户")
    st.markdown("- 产出：注册为用户策略插件，与内置策略一样参与回测和模拟交易")
    if st.button("打开 Python 编辑器", key="hub_goto_python", type="primary"):
        st.switch_page("pages/8_custom_strategy.py")

st.divider()
st.subheader("已保存的策略包")
st.caption("模板、积木与自然语言三种方式生成的策略都保存在这里，统一管理。")

config_path = "configs/app.yaml"  # 正式版固定配置路径，不再提供侧栏修改入口
try:
    studio = StrategyStudioService(BacktestService(config_path))
    packages = studio.store.list()
except Exception as exc:  # noqa: BLE001 - 配置损坏时给出可读提示而非崩溃
    st.error(f"无法读取策略包：{exc}")
    packages = ()

_SOURCE_LABELS = {
    "visual_builder": "积木编辑器",
    "nl_builder": "自然语言",
}
if not packages:
    st.info("还没有保存过策略包。先从上方任意一种方式创建一个吧。")
else:
    for package in packages:
        source = package.source
        if source.startswith("template:"):
            source_label = "模板"
        elif source.startswith("copy:"):
            source_label = "副本"
        else:
            source_label = _SOURCE_LABELS.get(source, source)
        with st.container(border=True):
            info_col, action_col = st.columns([4, 1])
            with info_col:
                st.markdown(
                    f"**{package.name}** ｜ 来源：{source_label} ｜ "
                    f"持股 {package.top_n} 只 ｜ 调仓：{package.rebalance}"
                )
                st.caption(
                    package.definition.describe(
                        top_n=package.top_n, rebalance=package.rebalance
                    )
                )
            with action_col:
                if st.button("去回测", key=f"hub_backtest_{package.package_id}"):
                    st.session_state["studio_focus_package"] = package.package_id
                    st.switch_page("pages/7_strategy_studio.py")
