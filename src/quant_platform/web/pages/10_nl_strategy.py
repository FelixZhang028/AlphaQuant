"""自然语言建策略页（反馈第 3 条）。

用户输入中文策略描述 -> 大模型转换为结构化规则 JSON -> 平台强校验并展示
中文解释 -> 用户确认后保存为策略包（与模板、积木同一注册与回测流程）。

模型沿用“设置”中的默认提供方；未配置模型时引导用户前往设置，或改用模板与积木。
"""

from __future__ import annotations

import streamlit as st

from quant_platform.agents_bridge.llm_settings import (
    PROVIDER_CATALOG,
    LLMSettingsStore,
)
from quant_platform.application.backtest_service import BacktestService
from quant_platform.application.strategy_studio_service import StrategyStudioService
from quant_platform.core.exceptions import ConfigurationError
from quant_platform.strategies.nl_builder import (
    NLStrategyBuilder,
    definition_explanation,
)
from quant_platform.web.embedded_page import is_embedded
from quant_platform.web.theme import inject_global_css
from trading_agents.llm.base import create_llm_client

inject_global_css()

if is_embedded("strategy_natural_language"):
    st.subheader("自然语言建策略")
else:
    st.title("自然语言建策略")
st.caption(
    "用大模型把一句话策略描述转成平台结构化规则。"
    "生成后请先核对中文解释，确认无误再保存；API Key 仅保存在本地。"
)

store = LLMSettingsStore()
config_path = "configs/app.yaml"  # 正式版固定配置路径，不再提供侧栏修改入口

provider = store.get_default_provider()
spec = PROVIDER_CATALOG[provider]
resolved = store.resolve(provider)
key_status = (
    "无需凭证" if not spec.requires_key else ("已配置" if resolved["api_key"] else "未配置")
)
with st.container(border=True):
    st.markdown(f"**当前模型：{spec.display_name} / {resolved['model'] or '—'}**")
    st.caption(f"凭证状态：{key_status}。自然语言建策略沿用全局默认模型。")
    st.page_link("pages/14_settings.py", label="研究设置", icon=":material/settings:")

# ------------------------------------------------------------ 策略描述 ----
description = st.text_area(
    "用一句话描述你的策略",
    placeholder="例如：5日均线高于20日均线并且放量时买入，按20日涨幅从强到弱选前5只",
    height=100,
    key="nl_description",
)
examples = st.expander("不知道怎么写？看看这些例子", expanded=False)
with examples:
    st.markdown(
        "- 5日均线高于20日均线并且近5日平均成交额大于2000万时买入，按20日涨幅从高到低排序\n"
        "- 收盘价突破过去60日最高价时买入，按10日涨幅从强到弱排序\n"
        "- 5日跌幅超过3%且收盘价仍在60日均线上方时买入，按5日跌幅从大到小排序"
    )

param_col1, param_col2 = st.columns(2)
with param_col1:
    top_n = st.number_input("持股数量", min_value=1, max_value=50, value=5, key="nl_top_n")
with param_col2:
    rebalance_label = st.selectbox(
        "调仓频率", ["每周", "每日", "每月"], key="nl_rebalance"
    )
rebalance = {"每日": "daily", "每周": "weekly", "每月": "monthly"}[rebalance_label]

# ------------------------------------------------------------ 生成与确认 ----
if st.button("生成策略规则", type="primary", key="nl_generate"):
    if not description.strip():
        st.warning("请先输入策略描述。")
    elif provider == "mock":
        st.error("Mock 离线模型不能生成自然语言策略，请在“设置 → AI 模型”中选择可用模型。")
    elif spec.requires_key and not resolved["api_key"]:
        st.error(f"{spec.display_name} 未配置 API Key，请先前往“设置 → AI 模型”完成配置。")
    elif provider == "custom" and not resolved["base_url"]:
        st.error("自定义模型缺少 Base URL，请先前往“设置 → AI 模型”完成配置。")
    else:
        try:
            client = create_llm_client(
                provider,
                model=resolved["model"],
                base_url=resolved["base_url"],
                api_key=resolved["api_key"],
                env_key_name=spec.env_key_name,
            )
        except Exception as exc:  # noqa: BLE001 - 未配置 key 时给出可读提示
            st.error(f"模型不可用：{exc}")
            st.info("未配置模型时，请改用「零代码策略工作台」的模板或积木编辑器。")
            st.stop()
        with st.spinner("大模型正在理解你的策略描述……"):
            try:
                definition = NLStrategyBuilder(client).generate(description)
            except ConfigurationError as exc:
                st.error(str(exc))
                st.stop()
            except Exception as exc:  # noqa: BLE001 - 网络/端点错误
                st.error(f"调用模型失败：{exc}")
                st.stop()
        st.session_state["nl_definition"] = definition

definition = st.session_state.get("nl_definition")
if definition is not None:
    st.subheader("生成结果（请核对）")
    explanation = definition_explanation(definition, top_n=top_n, rebalance=rebalance)
    st.markdown("```\n" + explanation + "\n```")
    with st.expander("查看结构化规则 JSON"):
        st.code(definition.to_json(), language="json")

    confirm_col, discard_col = st.columns([1, 1])
    with confirm_col:
        if st.button("确认并保存策略", type="primary", key="nl_confirm"):
            try:
                studio = StrategyStudioService(BacktestService(config_path))
                package = studio.store.save(
                    definition,
                    top_n=int(top_n),
                    rebalance=rebalance,
                    source="nl_builder",
                )
            except Exception as exc:  # noqa: BLE001
                st.error(f"保存失败：{exc}")
                st.stop()
            del st.session_state["nl_definition"]
            st.success(f"策略「{package.name}」已保存。")
            if st.button("去「策略创作中心」查看并回测", key="nl_goto_hub"):
                st.switch_page("pages/0_strategy_hub.py")
    with discard_col:
        if st.button("放弃，重新描述", key="nl_discard"):
            del st.session_state["nl_definition"]
            st.rerun()
