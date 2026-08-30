"""Streamlit page for exploring the XTick market-data HTTP APIs.

接口定义以 XTick 官方文档为准（http://www.xtick.top/assets/apidoc.json），
本页的所有表单（接口路径、请求参数、枚举选项、默认值）都由该文档动态生成，
避免手写路径/参数与官方不一致。

关键点：XTick 数据接口的"成功响应"是 ZIP 压缩包（内含 data.json），
而 HTTP 响应头却标成 application/json；失败时返回普通 JSON
{"code":-1,"message":"..."}。_request_xtick 统一处理这两种情况。
"""

from __future__ import annotations

from quant_platform.web.theme import inject_global_css

inject_global_css()


import io
import json
import os
import re
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

import pandas as pd
import requests
import streamlit as st

from quant_platform.web.exports import dataframe_to_csv_bytes

DEFAULT_BASE_URL = "http://api.xtick.top"
DEFAULT_TOKEN = "448f197d69e049b38051edca063f1487"

_CATALOG_URL = "http://www.xtick.top/assets/apidoc.json"
_CATALOG_FILE = Path(__file__).resolve().parent.parent / "assets" / "xtick_apidoc.json"

# 官方文档里个别参数名缺失/有误，这里做修正（key 为文档中的参数名）。
# /doc/hot/bidhistory 的第二个参数在文档里名字为空（demo URL 里显示为 "&=1"），
# 实测真实参数名是 seq（0=开盘数据，1=集合竞价最后一条数据）。
_PARAM_NAME_PATCH = {"": "seq"}

_DATE_PARAM_HINTS = ("startdate", "enddate", "tradedate")

_TAB_NAMES = {
    1: "行情数据",
    2: "盯盘数据",
    3: "核心数据",
    4: "短线热点",
    8: "量化因子",
    9: "金融指标",
}

_LABELS = {
    "type": "标的类型 type",
    "code": "代码 code",
    "fq": "复权 fq",
    "period": "周期 period",
    "startDate": "开始日期 startDate",
    "endDate": "结束日期 endDate",
    "tradeDate": "交易日期 tradeDate",
    "token": "Token",
    "symbol": "市场 symbol",
    "field": "字段 field",
    "minutes": "最近N分钟 minutes",
    "seq": "序号 seq",
    "option": "选项 option",
}


def _request_xtick(base_url: str, path: str, token: str, params: dict[str, str]) -> Any:
    """请求一个 XTick 数据接口并返回解析后的数据。

    兼容两种响应：
    - 成功：ZIP 压缩包，内含 data.json（一个 JSON 数组/对象）；
    - 失败：普通 JSON {"code": -1, "message": "..."}。
    """
    response = requests.get(
        f"{base_url.rstrip('/')}{path}",
        params={"token": token, **params},
        timeout=30,
    )
    response.raise_for_status()
    return _decode_xtick_response(response.content)


def _decode_xtick_response(content: bytes) -> Any:
    """把 XTick 的原始响应字节解码为 Python 对象。"""
    if content[:2] == b"PK":  # zip 魔数
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return json.loads(archive.read("data.json"))
    payload = json.loads(content.decode("utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("code"), int):
        code = payload["code"]
        if code not in (0, 200):
            raise RuntimeError(f"XTick 接口返回错误 [{code}]：{payload.get('message', '未知错误')}")
        if "data" in payload:
            return payload["data"]
    return payload


@st.cache_data(show_spinner=False)
def _load_catalog() -> list[dict[str, Any]]:
    """加载官方接口文档；本地有缓存文件则直接读，否则在线拉取并缓存。"""
    if _CATALOG_FILE.exists():
        return json.loads(_CATALOG_FILE.read_text("utf-8"))
    response = requests.get(_CATALOG_URL, timeout=30)
    response.raise_for_status()
    catalog = response.json()
    try:
        _CATALOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CATALOG_FILE.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), "utf-8")
    except OSError:
        pass
    return catalog


def _parse_range_options(range_str: str | None) -> list[tuple[str, str]]:
    """把官方文档的枚举串（"1-沪深京A股，2-沪深指数"）解析成 [(值, 含义), ...]。"""
    options: list[tuple[str, str]] = []
    for item in re.split(r"[，,]", range_str or ""):
        item = item.strip()
        if not item:
            continue
        if "-" in item:
            value, _, label = item.partition("-")
            options.append((value.strip(), label.strip()))
        else:
            options.append((item, item))
    return options


def _demo_defaults(demo_url: str | None) -> dict[str, str]:
    """从官方示例 URL 中提取各参数的默认值（去掉 token）。"""
    if not demo_url:
        return {}
    return dict(parse_qsl(urlparse(demo_url).query, keep_blank_values=True))


def _output_rename_map(api: dict[str, Any]) -> dict[str, str]:
    """按官方文档 outputParas 生成列名映射：原字段名 -> 中文描述（原字段名）。

    例如量化因子接口的 x001 -> "昨收价（x001）"。注意不同接口的同一字段名
    （如 x001）含义不同，因此映射必须按接口分别取自各自的 outputParas。
    """
    mapping: dict[str, str] = {}
    for para in api.get("outputParas") or []:
        name = para.get("name")
        desc = para.get("description")
        if not name or not desc:
            continue
        # 清洗描述：只取第一行，去掉换行及 "#" 注释部分
        desc = desc.splitlines()[0].strip()
        if not desc or desc == name:
            continue
        mapping[name] = f"{desc}（{name}）"
    return mapping


def _render_field(
    name: str, label: str, param: dict[str, Any], demo_defaults: dict[str, str], widget_key: str
) -> Any:
    """按参数定义渲染一个输入控件。"""
    kind = param.get("type", "String")
    default = demo_defaults.get(name, "")
    range_str = param.get("range")

    if range_str:
        options = _parse_range_options(range_str)
        labels = [f"{value} - {meaning}" for value, meaning in options]
        index = 0
        for i, (value, _meaning) in enumerate(options):
            if str(default) == str(value):
                index = i
                break
        return st.selectbox(
            label,
            labels,
            index=index,
            format_func=lambda item: item,
            help=f"枚举值：{range_str}",
            key=widget_key,
        )

    if kind.lower() in ("int", "long"):
        value = int(default) if str(default).lstrip("-").isdigit() else 0
        return st.number_input(label, value=value, step=1, help=f"类型：{kind}", key=widget_key)

    if kind.lower() in ("double", "float", "bigdecimal"):
        try:
            value = float(default) if default not in ("", None) else 0.0
        except ValueError:
            value = 0.0
        return st.number_input(label, value=value, step=0.01, help=f"类型：{kind}", key=widget_key)

    if name.lower() in _DATE_PARAM_HINTS:
        default_date = date.today() - timedelta(days=30) if name.lower() == "startdate" else date.today()
        return st.date_input(label, value=default_date, key=widget_key)

    return st.text_input(label, value=str(default) if default else "", key=widget_key)


def _strip_label(value: Any) -> Any:
    """select 选项带中文说明前缀（如 "1 - 沪深京A股"），提交前截取真实参数值。"""
    if isinstance(value, str) and " - " in value:
        return value.split(" - ", 1)[0]
    return value


def _download_csv(frame: pd.DataFrame, *, label: str, file_name: str, key: str) -> None:
    st.download_button(
        label=label,
        data=dataframe_to_csv_bytes(frame),
        file_name=file_name,
        mime="text/csv; charset=utf-8",
        key=key,
    )


def _to_frame(result: Any) -> pd.DataFrame | None:
    """把返回数据转成 DataFrame；不支持的结构返回 None（用 st.json 展示）。"""
    if isinstance(result, list):
        return pd.json_normalize(result) if result else pd.DataFrame()
    if isinstance(result, dict):
        inner = result.get("data")
        # 列式结构，如 {"code": [...], "name": [...], ...}
        if isinstance(inner, dict) and inner and all(isinstance(v, list) for v in inner.values()):
            return pd.DataFrame(inner)
        if result and all(isinstance(v, list) for v in result.values()):
            return pd.DataFrame(result)
        # 单行统计结构，如 {"time": ..., "shcje": ..., ...}
        if result and all(not isinstance(v, (dict, list)) for v in result.values()):
            return pd.DataFrame([result])
    return None


def _render_api_form(cat_id: int, api: dict[str, Any]) -> None:
    """按官方文档渲染一个接口的表单。"""
    api_id = api.get("id")
    form_key = f"{cat_id}_{api_id}"
    url = api.get("url")
    demo_defaults = _demo_defaults(api.get("demo"))

    st.markdown(f"**{api.get('name')}**  `{url}`")
    if api.get("description"):
        st.caption(api["description"])

    params: list[dict[str, Any]] = []
    for raw in api.get("inputParas", []):
        raw_name = raw.get("name") or ""
        if raw_name == "token":
            continue
        params.append(dict(raw, name=_PARAM_NAME_PATCH.get(raw_name, raw_name)))

    with st.form(f"xtick_form_{form_key}"):
        columns = st.columns(min(3, max(1, len(params)))) if params else [st]
        values: dict[str, Any] = {}
        for index, param in enumerate(params):
            name = param["name"]
            with columns[index % len(columns)]:
                values[name] = _render_field(
                    name,
                    _LABELS.get(name, name),
                    param,
                    demo_defaults,
                    f"xtick_{form_key}_{name}",
                )
        submitted = st.form_submit_button("请求数据", type="primary")

    if submitted:
        if not token:
            st.warning("请先在侧边栏填写 XTick Token。")
        else:
            request_params: dict[str, str] = {}
            for name, value in values.items():
                if isinstance(value, date):
                    request_params[name] = value.strftime("%Y-%m-%d")
                else:
                    request_params[name] = str(_strip_label(value))
            try:
                with st.spinner("正在请求 XTick 接口……"):
                    st.session_state[f"xtick_result_{form_key}"] = _request_xtick(
                        base_url, url, token, request_params
                    )
            except Exception as exc:
                st.error(f"请求失败：{exc}")
                st.session_state.pop(f"xtick_result_{form_key}", None)

    result = st.session_state.get(f"xtick_result_{form_key}")
    if result is None:
        return
    frame = _to_frame(result)
    if frame is not None:
        frame = frame.rename(columns=_output_rename_map(api))
        st.caption(f"返回 {len(frame):,} 行 × {frame.shape[1]:,} 列。")
        st.dataframe(frame, width="stretch", hide_index=True)
        with st.expander("原始 JSON"):
            st.json(result)
        _download_csv(
            frame,
            label="下载 CSV",
            file_name=f"xtick_{form_key}.csv",
            key=f"xtick_download_{form_key}",
        )
    else:
        st.json(result)
    st.divider()


st.title("XTick 数据服务")
st.caption(
    "调用 XTick 金融行情数据 HTTP API（http://www.xtick.top/doc）。"
    "接口表单由官方 apidoc.json 动态生成；认证方式为 URL 参数 token；"
    "成功响应为 ZIP 压缩包（内含 data.json），本页自动解包展示。"
)

token = st.sidebar.text_input(
    "XTick Token",
    value=os.environ.get("XTICK_TOKEN") or DEFAULT_TOKEN,
    type="password",
    help="请求必须携带 token；可在此修改，也可通过环境变量 XTICK_TOKEN 覆盖。",
)
base_url = st.sidebar.text_input("API Base URL", value=DEFAULT_BASE_URL)
if not token:
    st.sidebar.info("尚未配置 XTick Token，表单提交会被拦截。")

try:
    catalog = _load_catalog()
except Exception as exc:
    st.error(f"加载 XTick 接口文档失败：{exc}")
    st.stop()

tabs = st.tabs([_TAB_NAMES.get(category.get("id"), category.get("name")) for category in catalog])
for tab, category in zip(tabs, catalog):
    with tab:
        for api in category.get("docApis", []):
            _render_api_form(category.get("id"), api)
