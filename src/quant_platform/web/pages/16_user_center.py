"""Account center prototype with real profile data and explicit feature previews."""

from __future__ import annotations

import streamlit as st

from quant_platform.web.auth import AuthStore
from quant_platform.web.theme import inject_global_css

username = st.session_state.get("aq_authenticated_user")
if not username:
    st.warning("请先登录，再查看个人中心。")
    st.stop()

inject_global_css()
st.title("个人中心")
st.caption("管理你的账号，打造自己的研究空间。")

profile = AuthStore().get_profile(str(username))
if profile is None:
    st.warning("未找到当前账号资料，请退出后重新登录。")

with st.container(border=True):
    identity, action = st.columns([3, 1], vertical_alignment="center")
    with identity:
        st.subheader(f":material/account_circle: {username}")
        st.caption("已登录 · FellowQuant 研究工作台")
    with action:
        if st.button("返回上一页", icon=":material/arrow_back:", key="account_center_back"):
            st.switch_page(
                st.session_state.get("aq_account_return_page", "pages/15_workspace_home.py")
            )

section = st.segmented_control(
    "个人中心分类",
    ["个人资料", "账号安全", "使用偏好", "我的研究"],
    default="个人资料",
    label_visibility="collapsed",
    key="account_center_section",
)

if section == "个人资料":
    with st.container(border=True):
        st.subheader(":material/person: 基本资料")
        st.caption("以下信息来自注册账号，资料编辑功能即将开放。")
        left, right = st.columns(2)
        with left:
            st.text_input("用户名", value=str(username), disabled=True)
            st.text_input(
                "邮箱", value=str(profile["email"]) if profile else "—", disabled=True
            )
        with right:
            st.text_input(
                "用户 ID", value=str(profile["id"]) if profile else "—", disabled=True
            )
            st.text_input(
                "注册时间（UTC）",
                value=str(profile["created_at"]) if profile else "—",
                disabled=True,
            )
        st.button("编辑资料 · 即将开放", icon=":material/edit:", disabled=True)

elif section == "账号安全":
    with st.container(border=True):
        st.subheader(":material/lock: 登录密码")
        st.caption("修改密码功能即将开放。")
        st.button("修改密码 · 即将开放", disabled=True)
    with st.container(border=True):
        st.subheader(":material/devices: 当前会话")
        st.write("退出后需要重新登录才能进入工作台，当前未保存的输入将被清除。")
        if st.button("退出登录", icon=":material/logout:", key="account_center_logout"):
            for key in list(st.session_state):
                del st.session_state[key]
            st.rerun()

elif section == "使用偏好":
    with st.container(border=True):
        st.subheader(":material/tune: 工作台偏好")
        st.caption("功能预览：以下选项暂未启用，不会更改当前设置。")
        st.selectbox("默认进入页面", ["首页", "AI研究员", "策略工作室"], disabled=True)
        st.selectbox("界面语言", ["简体中文", "English"], disabled=True)
        st.button("保存偏好 · 即将开放", disabled=True)
    with st.container(border=True):
        st.subheader(":material/settings: 模型与数据源")
        st.caption("当前配置作用于本机工作台，尚未按账号独立保存。")
        st.page_link("pages/14_settings.py", label="前往设置", icon=":material/arrow_forward:")

elif section == "我的研究":
    st.info("个人研究空间即将开放，完成数据归属配置后，将展示你自己的研究成果。")
    for column, title, description, icon in zip(
        st.columns(3),
        ["我的策略", "回测记录", "我的收藏"],
        ["集中管理自己创建的策略。", "回顾个人回测与验证结果。", "快速找到收藏的研究内容。"],
        [":material/code:", ":material/history:", ":material/bookmark:"],
        strict=True,
    ):
        with column:
            with st.container(border=True):
                st.subheader(f"{icon} {title}")
                st.write(description)
                st.caption("即将开放")
