"""Manage the human knowledge that constrains AI research."""

from __future__ import annotations

import streamlit as st

from quant_platform.agents_bridge.prior_knowledge import PriorKnowledgeStore
from quant_platform.web.theme import inject_global_css

inject_global_css()

st.title("先验知识库")
st.caption("集中维护你认可的事实、判断和约束；AI 投研时会把这些内容作为明确边界。")

store = PriorKnowledgeStore()
entries = store.list()
sources = sorted({entry.source for entry in entries})

summary = st.columns(3)
summary[0].metric("知识条目", len(entries))
summary[1].metric("来源数量", len(sources))
summary[2].metric("最近更新", entries[0].created_at.date().isoformat() if entries else "—")

view = st.segmented_control(
    "知识库操作",
    ["浏览知识", "新增知识"],
    default="浏览知识",
    key="prior_knowledge_view",
    label_visibility="collapsed",
)

if view == "新增知识":
    with st.container(border=True):
        st.subheader("新增先验知识")
        st.caption("一条只写一个明确观点，并注明来源，方便后续核对和删除。")
        with st.form("prior_library_add"):
            content = st.text_area(
                "知识内容",
                placeholder="例如：公司未来六个月存在较大的限售股解禁压力，仓位上限应降低。",
                height=120,
            )
            source = st.text_input(
                "来源",
                placeholder="我的判断 / 研究报告 / 网页链接",
            )
            submitted = st.form_submit_button(
                "保存知识", type="primary", icon=":material/save:"
            )
        if submitted:
            try:
                store.add(content, source)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.success("先验知识已保存，并会用于后续 AI 投研。")
                st.rerun()
else:
    if not entries:
        st.info("知识库还是空的。先新增一条你希望 AI 必须参考的判断。")
    else:
        filter_columns = st.columns([2, 1])
        with filter_columns[0]:
            query = st.text_input(
                "搜索知识",
                placeholder="搜索内容或来源",
                key="prior_library_query",
            ).strip().lower()
        with filter_columns[1]:
            selected_source = st.selectbox(
                "来源筛选", ["全部来源", *sources], key="prior_library_source"
            )

        filtered = [
            entry
            for entry in entries
            if (selected_source == "全部来源" or entry.source == selected_source)
            and (not query or query in entry.content.lower() or query in entry.source.lower())
        ]
        st.caption(f"当前显示 {len(filtered)} 条；AI 投研仍会使用全部 {len(entries)} 条。")
        if not filtered:
            st.info("没有符合当前筛选条件的知识。")
        for entry in filtered:
            with st.container(border=True):
                st.markdown(entry.content)
                st.caption(
                    f"来源：{entry.source} ｜ 更新时间："
                    f"{entry.created_at.astimezone().strftime('%Y-%m-%d %H:%M')}"
                )
                if st.button(
                    "删除",
                    key=f"prior_library_delete_{entry.id}",
                    icon=":material/delete:",
                ):
                    store.delete(entry.id)
                    st.success("该条知识已删除。")
                    st.rerun()

with st.expander("AI 如何使用这些知识"):
    st.write(
        "运行 AI 投研时，系统会把全部条目连同来源注入分析上下文。"
        "AI 可以指出数据与先验知识的冲突，但不能静默忽略这些约束。"
    )
