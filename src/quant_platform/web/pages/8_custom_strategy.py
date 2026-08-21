"""Advanced mode: write, upload, and run custom Python strategies."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import streamlit as st

from quant_platform.application.backtest_service import BacktestService
from quant_platform.core.exceptions import BacktestValidityError
from quant_platform.strategies.spec import ParameterKind, StrategyParameter
from quant_platform.user_strategies.loader import UserStrategyLoader
from quant_platform.user_strategies.starter import STARTER_STRATEGY_CODE
from quant_platform.user_strategies.store import UserStrategyStore

_REBALANCE_LABELS = {"daily": "每日", "weekly": "每周", "monthly": "每月"}


def _rebalance_label(value: str) -> str:
    return _REBALANCE_LABELS.get(value, value)


def _parameter_input(
    parameter: StrategyParameter, value: int | float | bool | str, *, key_prefix: str
) -> int | float | bool | str:
    """Render one strategy parameter; user parameters are introspected."""

    help_text = parameter.description or None
    key = f"{key_prefix}_{parameter.name}"
    if parameter.choices:
        choices = list(parameter.choices)
        default_index = choices.index(str(value)) if str(value) in choices else 0
        return st.selectbox(parameter.label, choices, index=default_index, help=help_text, key=key)
    if parameter.kind == ParameterKind.INTEGER:
        return int(
            st.number_input(
                parameter.label,
                value=int(value),
                min_value=(int(parameter.minimum) if parameter.minimum is not None else None),
                max_value=(int(parameter.maximum) if parameter.maximum is not None else None),
                step=1,
                help=help_text,
                key=key,
            )
        )
    if parameter.kind == ParameterKind.NUMBER:
        return float(
            st.number_input(
                parameter.label,
                value=float(value),
                min_value=(float(parameter.minimum) if parameter.minimum is not None else None),
                max_value=(float(parameter.maximum) if parameter.maximum is not None else None),
                help=help_text,
                key=key,
            )
        )
    if parameter.kind == ParameterKind.BOOLEAN:
        return st.checkbox(parameter.label, value=bool(value), help=help_text, key=key)
    return st.text_input(parameter.label, value=str(value), help=help_text, key=key)


def _save_user_strategy(
    store: UserStrategyStore,
    loader: UserStrategyLoader,
    code: str,
    display_name: str,
    description: str,
    source: str,
) -> None:
    """Load code, validate the registered class, and persist it."""

    if not code.strip():
        st.error("策略代码不能为空。")
        return
    result = loader.load_source(code, label=source)
    if not result.strategies:
        for _, message in result.errors:
            st.error(message)
        if not result.errors:
            st.error("没有发现已注册的策略，请使用 @register_strategy(\"标识\") 装饰策略类。")
        return
    if len(result.strategies) > 1:
        st.warning("代码注册了多个策略，本次只保存第一个。")
    plugin_name, cls = next(iter(result.strategies.items()))
    try:
        record = store.save(
            code,
            plugin_name=plugin_name,
            display_name=display_name.strip() or cls.display_name,
            description=description.strip() or cls.description,
            source=source,
        )
    except Exception as exc:
        st.error(f"保存失败：{exc}")
        return
    st.session_state["custom_strategy_flash"] = (
        f"已保存策略：{record.display_name}（{plugin_name}）"
    )
    st.rerun()


def _remember_result(run: Any, state_key: str) -> None:
    st.session_state[state_key] = {
        "run_id": str(run.result.run_id),
        "summary": dict(run.result.summary),
    }


def _show_result(state_key: str) -> None:
    remembered = st.session_state.get(state_key)
    if not isinstance(remembered, dict):
        return
    run_id = str(remembered.get("run_id", ""))
    summary = remembered.get("summary", {})
    if not run_id or not isinstance(summary, dict):
        return
    st.success("回测已完成并保存。")
    columns = st.columns(4)
    columns[0].metric("累计收益", f"{float(summary.get('cumulative_return', 0)):.2%}")
    columns[1].metric("最大回撤", f"{float(summary.get('max_drawdown', 0)):.2%}")
    columns[2].metric("夏普比率", f"{float(summary.get('sharpe', 0)):.2f}")
    columns[3].metric("成交笔数", str(summary.get("fills", 0)))
    if st.button("打开完整回测结果", key=f"open_{state_key}_{run_id}"):
        st.session_state["selected_run"] = run_id
        st.switch_page("home.py")


st.title("自定义策略（Python）")
st.caption("继承 BaseStrategy 并注册，平台会加载你的代码、自动生成参数表单并回测。")

flash = st.session_state.pop("custom_strategy_flash", None)
if flash:
    st.success(flash)

st.warning("高级模式会运行你自己编写的 Python 代码，请只保存你信任的代码。")

config_path = st.sidebar.text_input("平台配置", "configs/app.yaml", key="custom_strategy_config")
try:
    backtests = BacktestService(config_path)
    default_request = backtests.default_request()
except Exception as exc:
    st.error(f"无法加载平台服务：{exc}")
    st.stop()

store = UserStrategyStore(backtests.user_strategy_root)
loader = UserStrategyLoader()

if backtests.user_strategy_errors:
    with st.expander("部分已保存策略加载失败", expanded=False):
        for name, message in backtests.user_strategy_errors:
            st.caption(f"· {name}：{message}")

editor_tab, upload_tab, library_tab = st.tabs(["编写策略", "上传文件", "我的策略"])

with editor_tab:
    st.subheader("在网页上编写策略")
    if "custom_strategy_code" not in st.session_state:
        st.session_state["custom_strategy_code"] = STARTER_STRATEGY_CODE
    code = st.text_area("策略代码", height=540, key="custom_strategy_code")
    st.caption(
        "用 @register_strategy(\"唯一英文标识\") 注册；__init__ 的参数需带默认值，"
        "平台据此自动生成参数表单。"
    )
    with st.form("custom_strategy_editor_form"):
        display_name = st.text_input("策略显示名（可选，默认用标识）", key="editor_display_name")
        description = st.text_area("策略说明（可选）", height=70, key="editor_description")
        submitted = st.form_submit_button("注册并保存", type="primary")
    if submitted:
        _save_user_strategy(
            store, loader, code, display_name, description, source="editor"
        )

with upload_tab:
    st.subheader("上传写好的 .py 策略文件")
    uploaded = st.file_uploader("选择策略文件", type=["py"])
    if uploaded is not None:
        try:
            raw = uploaded.getvalue().decode("utf-8")
        except UnicodeDecodeError:
            st.error("文件不是有效的 UTF-8 文本。")
        else:
            st.code(raw, language="python")
            with st.form("custom_strategy_upload_form"):
                upload_display_name = st.text_input(
                    "策略显示名（可选）", key="upload_display_name"
                )
                upload_description = st.text_area(
                    "策略说明（可选）", height=70, key="upload_description"
                )
                upload_submitted = st.form_submit_button("注册并保存该文件", type="primary")
            if upload_submitted:
                _save_user_strategy(
                    store,
                    loader,
                    raw,
                    upload_display_name,
                    upload_description,
                    source="upload",
                )

with library_tab:
    st.subheader("我的自定义策略")
    records = store.list()
    if not records:
        st.info("还没有自定义策略。请先在“编写策略”或“上传文件”中注册并保存。")
    else:
        record_by_plugin = {record.plugin_name: record for record in records}
        plugin = st.selectbox(
            "选择策略",
            list(record_by_plugin),
            format_func=lambda value: f"{record_by_plugin[value].display_name}｜{value}",
        )
        record = record_by_plugin[plugin]
        st.caption(record.description or "（无说明）")
        with st.expander("查看源码", expanded=False):
            st.code(record.read_code(), language="python")

        try:
            metadata = backtests.catalog.get_metadata(plugin)
        except Exception as exc:
            st.error(f"策略加载失败：{exc}")
        else:
            with st.form(f"custom_strategy_run_{plugin}"):
                parameter_values: dict[str, Any] = {}
                parameter_columns = st.columns(2)
                for index, parameter in enumerate(metadata.parameters):
                    with parameter_columns[index % 2]:
                        parameter_values[parameter.name] = _parameter_input(
                            parameter, parameter.default, key_prefix=f"run_{plugin}"
                        )
                left, middle, right = st.columns(3)
                start_date = left.date_input(
                    "开始日期", default_request.start_date, key=f"sd_{plugin}"
                )
                end_date = middle.date_input(
                    "结束日期", default_request.end_date, key=f"ed_{plugin}"
                )
                initial_cash = right.number_input(
                    "初始资金",
                    min_value=1_000.0,
                    value=default_request.initial_cash,
                    key=f"ic_{plugin}",
                )
                left2, middle2, right2 = st.columns(3)
                top_n = int(
                    left2.number_input(
                        "持股数量",
                        min_value=1,
                        max_value=50,
                        value=default_request.top_n,
                        step=1,
                        key=f"tn_{plugin}",
                    )
                )
                rebalance = middle2.selectbox(
                    "调仓频率",
                    ["daily", "weekly", "monthly"],
                    index=["daily", "weekly", "monthly"].index(default_request.rebalance),
                    format_func=_rebalance_label,
                    key=f"rb_{plugin}",
                )
                run_submitted = right2.form_submit_button("运行回测", type="primary")

            if run_submitted:
                request = replace(
                    default_request,
                    strategy_plugin=plugin,
                    strategy_id=f"{plugin}_web",
                    strategy_parameters=parameter_values,
                    start_date=start_date,
                    end_date=end_date,
                    initial_cash=float(initial_cash),
                    top_n=top_n,
                    rebalance=rebalance,
                )
                try:
                    with st.spinner("正在运行回测……"):
                        completed = backtests.run(request)
                    _remember_result(completed, f"custom_run_{plugin}")
                except BacktestValidityError as exc:
                    st.error(f"回测已停止：{exc}")
                except Exception as exc:
                    st.exception(exc)
            _show_result(f"custom_run_{plugin}")

        if st.button("删除该策略", key=f"delete_{plugin}"):
            store.delete(plugin)
            st.session_state["custom_strategy_flash"] = f"已删除策略：{plugin}"
            st.rerun()

st.divider()
st.caption(
    "安全边界：高级模式在本地进程中运行你提供的 Python 代码，导入受限但并非强隔离；"
    "请仅运行你信任的策略代码，并遵守平台的信号/组合/风控约定。"
)
