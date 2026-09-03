"""Central settings for models, data credentials, network, and runtime status."""

from __future__ import annotations

import os
import platform
import shutil
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pandas as pd
import streamlit as st

from quant_platform.agents_bridge.data_credentials import (
    DEFAULT_DATA_CREDENTIALS_PATH,
    DataCredentialStore,
)
from quant_platform.agents_bridge.llm_settings import (
    DEFAULT_SETTINGS_PATH,
    PROVIDER_CATALOG,
    LLMSettingsStore,
)
from quant_platform.agents_bridge.proxy_settings import ProxySettingsStore
from quant_platform.core.config import load_yaml, require_mapping
from quant_platform.web.theme import inject_global_css

inject_global_css()

st.title("设置")
st.caption("集中管理模型、数据凭证和本地运行环境。")

section = st.segmented_control(
    "设置分类",
    ["AI 模型", "数据源凭证", "网络与存储", "系统信息"],
    default="AI 模型",
    key="settings_section",
    label_visibility="collapsed",
    width="stretch",
)

if section == "AI 模型":
    store = LLMSettingsStore()
    provider_keys = list(PROVIDER_CATALOG)
    default_provider = store.get_default_provider()

    st.subheader("AI 模型")
    st.caption("业务页面优先使用这里选择的默认模型；各提供方凭证只保存在本机。")

    selected_default = st.selectbox(
        "默认模型提供方",
        provider_keys,
        index=provider_keys.index(default_provider),
        format_func=lambda key: PROVIDER_CATALOG[key].display_name,
        key="settings_default_llm_provider",
    )
    if st.button("设为默认", icon=":material/check:", key="save_default_provider"):
        store.save_default_provider(selected_default)
        st.success(f"已将 {PROVIDER_CATALOG[selected_default].display_name} 设为默认。")

    provider = st.selectbox(
        "配置提供方",
        provider_keys,
        index=provider_keys.index(selected_default),
        format_func=lambda key: PROVIDER_CATALOG[key].display_name,
        key="settings_llm_provider",
    )
    spec = PROVIDER_CATALOG[provider]
    saved = store.get(provider)
    resolved = store.resolve(provider)
    status = "无需凭证" if not spec.requires_key else ("已配置" if resolved["api_key"] else "未配置")
    st.info(f"当前模型：{resolved['model'] or '—'} ｜ 凭证状态：{status}")

    with st.form("settings_llm_form"):
        base_url = st.text_input(
            "Base URL",
            value=saved["base_url"] or spec.default_base_url,
            disabled=not bool(spec.default_base_url) and provider == "mock",
        )
        api_key = st.text_input(
            "API Key",
            value=saved["api_key"],
            type="password",
            disabled=not spec.requires_key,
            help="留空时回退到该提供方对应的环境变量。",
        )
        models = list(spec.models)
        current_model = saved["model"] or spec.default_model
        if current_model and current_model not in models:
            models.append(current_model)
        if models:
            model = st.selectbox(
                "模型",
                models,
                index=models.index(current_model) if current_model in models else 0,
            )
        else:
            model = st.text_input("模型", value=current_model)
        save_llm = st.form_submit_button(
            "保存模型配置", type="primary", icon=":material/save:"
        )
    if save_llm:
        store.save(
            provider,
            base_url=base_url.strip(),
            api_key=api_key.strip(),
            model=model.strip(),
        )
        st.success(f"{spec.display_name} 配置已保存到本地。")
    st.caption(f"本地配置文件：{DEFAULT_SETTINGS_PATH}")

elif section == "数据源凭证":
    store = DataCredentialStore()
    store.load_into_environment()
    st.subheader("数据源凭证")
    st.caption("这里只管理认证信息；数据源对比与使用入口位于“数据资产”。")

    status_rows = [
        {
            "数据源": "XTick",
            "凭证类型": "Token",
            "状态": "已配置" if store.resolve("xtick", "token", "XTICK_TOKEN") else "未配置",
        },
        {
            "数据源": "iFinD",
            "凭证类型": "账号与密码",
            "状态": (
                "已配置"
                if store.resolve("ifind", "username", "IFIND_USERNAME")
                and store.resolve("ifind", "password", "IFIND_PASSWORD")
                else "未配置"
            ),
        },
        {
            "数据源": "Tushare",
            "凭证类型": "Token",
            "状态": (
                "已配置"
                if store.resolve("tushare", "token", "TUSHARE_TOKEN")
                else "未配置"
            ),
        },
        {"数据源": "BaoStock / AkShare", "凭证类型": "无需", "状态": "可直接使用"},
    ]
    st.dataframe(pd.DataFrame(status_rows), hide_index=True, width="stretch")

    provider = st.selectbox(
        "选择要配置的数据源",
        ["XTick", "iFinD", "Tushare"],
        key="settings_data_provider",
    )
    provider_key = provider.lower()
    current = store.get(provider_key)
    with st.form("settings_data_credentials_form"):
        if provider == "iFinD":
            username = st.text_input("账号", value=current.get("username", ""))
            password = st.text_input(
                "密码", value=current.get("password", ""), type="password"
            )
            values = {"username": username, "password": password}
        else:
            token = st.text_input(
                "Token", value=current.get("token", ""), type="password"
            )
            values = {"token": token}
            if provider == "XTick":
                base_url = st.text_input(
                    "API Base URL",
                    value=current.get("base_url", "http://api.xtick.top"),
                )
                values["base_url"] = base_url
        save_credentials = st.form_submit_button(
            "保存凭证", type="primary", icon=":material/save:"
        )
    if save_credentials:
        store.save(provider_key, **values)
        st.success(f"{provider} 凭证已保存到本地。")
        st.rerun()
    st.caption(f"本地配置文件：{DEFAULT_DATA_CREDENTIALS_PATH}")

elif section == "网络与存储":
    proxy_store = ProxySettingsStore()
    proxy = proxy_store.load()
    st.subheader("网络与存储")
    st.caption("网络设置只影响需要联网的外部来源，不改变研究与回测规则。")

    with st.form("settings_proxy_form"):
        proxy_enabled = st.toggle("为海外数据源启用代理", value=bool(proxy["enabled"]))
        proxy_address = st.text_input("代理地址", value=str(proxy["address"]))
        save_proxy = st.form_submit_button(
            "保存网络设置", type="primary", icon=":material/save:"
        )
    if save_proxy:
        proxy_store.save(proxy_enabled, proxy_address)
        st.success("网络设置已保存。")

    try:
        app_config = load_yaml("configs/app.yaml")
        repository = str(require_mapping(app_config, "data")["repository"])
        runtime_dir = str(require_mapping(app_config, "app")["runtime_dir"])
    except Exception:
        repository, runtime_dir = "—", "runtime"
    storage = st.columns(2)
    with storage[0].container(border=True):
        st.markdown("**本地数据目录**")
        st.code(repository)
        st.caption("行情、证券主表和数据版本保存在这里。")
    with storage[1].container(border=True):
        st.markdown("**运行记录目录**")
        st.code(runtime_dir)
        st.caption("回测、验证、模拟账户和本地设置保存在这里。")

else:
    st.subheader("系统信息")
    try:
        app_version = version("quant-platform")
    except PackageNotFoundError:
        app_version = "开发版"
    disk = shutil.disk_usage(Path.cwd())
    metrics = st.columns(4)
    metrics[0].metric("平台版本", app_version)
    metrics[1].metric("Python", platform.python_version())
    metrics[2].metric("Streamlit", st.__version__)
    metrics[3].metric("磁盘可用", f"{disk.free / 1024**3:.1f} GB")

    system_rows = [
        {"项目": "操作系统", "值": platform.platform()},
        {"项目": "Python 可执行文件", "值": sys.executable},
        {"项目": "工作目录", "值": str(Path.cwd())},
        {"项目": "本地设置目录", "值": str(Path("runtime").resolve())},
        {"项目": "代理环境", "值": "已设置" if os.getenv("HTTPS_PROXY") else "未设置"},
    ]
    st.dataframe(pd.DataFrame(system_rows), hide_index=True, width="stretch")
