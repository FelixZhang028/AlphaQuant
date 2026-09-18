"""Pytest 全局配置与第三方库兼容补丁。

补丁集中放在此处，避免散落在各测试文件中；上游库修复对应问题后可移除。
"""
from __future__ import annotations

import json

# --- Streamlit 1.50.0 AppTest 兼容补丁 ----------------------------------
# 补丁 1：官方测试类 ButtonGroup.indices 假设 widget 值为 list；但单选
# segmented_control 等单选型 button_group 的值是标量字符串，原实现
# 会对标量做逐字符迭代（如 "个人资料" -> "个"），导致 options.index
# 抛出 ValueError，中文选项值首字符出现在报错信息中即此原因。
# 此处重写为标量安全的版本，行为对多选（list）完全不变。

from streamlit.testing.v1 import element_tree as _et
from streamlit.testing.v1.element_tree import ButtonGroup as _ButtonGroup


def _button_group_indices_compat(self):  # noqa: ANN001, ANN202
    value = self.value
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        value = [value]
    return [self.options.index(self.format_func(v)) for v in value]


_ButtonGroup.indices = property(_button_group_indices_compat)

# 补丁 2：官方 AppTest 未提供 st.dataframe 行选择适配器，且 1.50.0 中
# Dataframe 元素不再是 Widget（.key 恒为 None），旧的
# ``app.session_state[df.key] = {...}`` 注入会写入 None 键并在 rerun
# 时触发 _compact_state 崩溃。此补丁让元素树回放时同时收集 Dataframe
# 实例上的 ``_test_selection`` 属性，按官方 string_value 事件格式回放，
# 测试侧用 ``app.dataframe[0]._test_selection = {...}`` 模拟行选择。


def _get_widget_states_with_dataframe(self):  # noqa: ANN001, ANN202
    ws = _et.WidgetStates()
    for node in self:
        w = _et.get_widget_state(node)
        if w is not None:
            ws.widgets.append(w)
        elif isinstance(node, _et.Dataframe):
            selection = getattr(node, "_test_selection", None)
            if selection is not None:
                state = _et.WidgetState()
                state.id = node.proto.id
                state.string_value = json.dumps(selection)
                ws.widgets.append(state)
    return ws


_et.ElementTree.get_widget_states = _get_widget_states_with_dataframe

