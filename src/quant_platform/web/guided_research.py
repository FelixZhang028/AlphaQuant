"""Beginner workflow using the existing factor strategy and backtest engine."""

import hashlib
from copy import deepcopy
from datetime import date

import streamlit as st

from quant_platform.application.backtest_service import BacktestService
from quant_platform.application.data_service import DataCenterService
from quant_platform.application.guided_research import IDEAS, idea_request, inspect_request
from quant_platform.core.diagnostics import public_data_error
from quant_platform.factors.registry import default_registry
from quant_platform.web.research_plans import ensure_plan, link_plan_run, render_plan_save
from quant_platform.web.security_names import load_security_names, security_label


def render_guided_research():
    st.subheader("验证我的选股想法")
    st.caption("选择想法 → 确认规则 → 检查数据 → 运行回测")
    try:
        service = BacktestService("configs/app.yaml")
        restored = st.session_state.get("restored_plan")
        if restored and restored["inputs"].get("idea"):
            service.configs = deepcopy(restored["snapshot"])
        defaults = service.default_request()
    except Exception:
        st.error("研究配置暂时无法加载，请先检查设置。")
        return
    draft = st.session_state.setdefault("guided_draft", {})
    initial = {
        "idea": "趋势上涨",
        "start": defaults.start_date,
        "end": defaults.end_date,
        "cash": defaults.initial_cash,
        "top_n": defaults.top_n,
        "rebalance": "weekly",
        "symbols": list(service.configs["universe"]["universe"]["symbols"]),
    }
    for field, value in initial.items():
        draft.setdefault(field, value)
        st.session_state.setdefault("_guided_" + field, draft[field])

    def remember(field):
        draft[field] = st.session_state["_guided_" + field]

    def widget_args(field):
        return {"key": "_guided_" + field, "on_change": remember, "args": (field,)}

    st.markdown("**1. 你想研究什么？**")
    idea = st.radio("选股想法", list(IDEAS), horizontal=True, **widget_args("idea"))
    factor_name, explanation = IDEAS[idea]
    factor = default_registry().get(factor_name)
    st.info(f"推荐因子：{factor.display_name}。{explanation}")
    st.caption("这是用于验证想法的起点，不代表已证实有效，也不保证收益。")
    st.markdown("**2. 设置研究范围**")
    configured = list(service.configs["universe"]["universe"]["symbols"])
    names = load_security_names()
    st.session_state["_guided_symbols"] = [
        s for s in st.session_state["_guided_symbols"] if s in configured
    ]
    symbols = st.multiselect(
        "从当前配置股票池选择",
        configured,
        format_func=lambda s: security_label(s, names),
        **widget_args("symbols"),
    )
    st.caption("当前成分固定回放，可能存在选择偏差。可在“数据资产 → 股票池”维护候选股票。")
    left, right = st.columns(2)
    with left:
        start = st.date_input("开始日期", **widget_args("start"))
        top_n = st.number_input(
            "最多持有几只股票", min_value=1, max_value=100, step=1, **widget_args("top_n")
        )
    with right:
        end = st.date_input("结束日期", **widget_args("end"))
        frequency = st.selectbox(
            "多久调整一次持仓",
            ["daily", "weekly", "monthly"],
            format_func=lambda s: {"daily": "每日", "weekly": "每周", "monthly": "每月"}[s],
            **widget_args("rebalance"),
        )
    with st.expander("更多设置"):
        cash = st.number_input("初始资金", min_value=1000.0, **widget_args("cash"))
        st.caption("采用等权目标持仓，并使用平台已配置的手续费、成交量限制和风险规则。")
        st.page_link("home.py", label="前往回测与验证查看高级设置")

    service.configs = deepcopy(service.configs)
    universe = service.configs["universe"]["universe"]
    universe["symbols"] = symbols
    universe.setdefault("filters", {})["exclude_st"] = True
    universe["filters"]["exclude_suspended"] = True
    request = idea_request(service, idea, start, end, cash, top_n, frequency)
    signature = hashlib.sha256(repr((request, symbols, service.configs)).encode()).hexdigest()
    if draft.get("signature") != signature:
        draft["signature"] = signature
        draft.pop("checks", None)
        draft.pop("run_id", None)
        draft.pop("update_message", None)
    st.markdown("**3. 确认实际执行规则**")
    frequency_label = {"daily": "每日", "weekly": "每周", "monthly": "每月"}[frequency]
    st.write(
        f"在所选 {len(symbols)} 只股票中排除 ST、停牌及不满足平台上市历史和成交额要求的股票。"
        f"{explanation}按因子方向打分，{frequency_label}"
        f"选取前 {top_n} 只，等权分配目标仓位；合格股票不足时不强行补足。"
    )
    st.caption(
        f"因子缺失样本不参与选股；先去极值再标准化。研究区间 {start} 至 {end}。"
        "最终成交受资金、交易限制和风控影响，可能低于目标仓位。"
    )
    filters = universe["filters"]
    required_history = max(
        int(filters.get("minimum_history_days", 61)), int(filters.get("minimum_listing_days", 0))
    )
    st.caption(
        f"股票筛选：至少 {required_history} 条历史，近20日平均成交额至少 "
        f"{float(filters.get('minimum_average_amount', 0)):,.0f} 元。"
    )
    limits = request.risk_limits
    count = min(top_n, len(symbols))
    allocation_ok = not limits.enabled or (
        count > 0
        and 1 / count <= limits.max_single_weight + 1e-9
        and count <= limits.max_positions
        and limits.max_total_weight >= 1
        and limits.minimum_cash_ratio == 0
    )
    if not allocation_ok:
        st.warning(
            f"当前等权方案与风险限制不兼容（单股上限 {limits.max_single_weight:.0%}，"
            f"最多 {limits.max_positions} 只）。请增加候选股和持仓数量，"
            "或在“回测与验证 → 风险规则”调整限制后再运行。"
        )
    confirmed = st.checkbox("我已确认以上规则符合我的想法", key="guided_confirm_" + signature)
    inputs = {field: draft[field] for field in initial}
    render_plan_save(service, request, draft, scope="guided", inputs=inputs)
    if not symbols or start > end or end > date.today():
        st.warning("请选择股票，并使用开始日期不晚于结束日期、结束日期不晚于今天的区间。")
        return
    st.markdown("**4. 检查数据并运行**")
    st.caption("检查依据本地交易日历；通过后，回测引擎仍会进行完整有效性审计。")
    if st.button("检查本次研究数据", key="guided_check"):
        try:
            with st.spinner("正在检查区间、回看历史和比较基准……"):
                draft["checks"] = inspect_request(service, request)
        except Exception:
            st.error("数据检查未能完成，请检查股票池、数据配置及高级风险规则。")
    checks = draft.get("checks")
    ready = checks is not None and checks["状态"].eq("通过").all()
    if checks is not None:
        st.dataframe(checks, hide_index=True, width="stretch")
        if not ready:
            st.warning("仍有数据缺口，请补齐后重新检查。你的研究设置会保留。")
    if st.button(
        "补齐本次研究数据并重新检查", key="guided_update", disabled=checks is None or ready
    ):
        try:
            data = DataCenterService("configs/app.yaml")
            data.universe_config = deepcopy(data.universe_config)
            data.universe_config["universe"]["symbols"] = symbols
            engine, _ = service.build_engine(request)
            with st.spinner("正在更新所选股票及基准，完成后自动复查……"):
                results = data.update_all(engine._warmup_start_date(start), end)
                draft["checks"] = inspect_request(service, request)
            failed = [r for r in results if r.status == "FAILED"]
            draft["update_message"] = (
                "部分数据更新失败："
                + "；".join(sorted({public_data_error(r.error) for r in failed}))
                if failed
                else "数据更新完成，已重新检查。"
            )
            st.rerun()
        except Exception as exc:
            st.error(public_data_error(exc))
            st.caption("研究设置已保留，可重试更新或前往数据资产检查。")
    if draft.get("update_message"):
        st.info(draft["update_message"])
    if st.button(
        "确认并运行回测",
        type="primary",
        key="guided_run",
        disabled=not (confirmed and ready and allocation_ok),
    ):
        try:
            # Recheck after changes on disk; never rely on a stale UI green light.
            draft["checks"] = inspect_request(service, request)
            if not draft["checks"]["状态"].eq("通过").all():
                st.rerun()
            with st.spinner("正在运行回测，完成后可查看完整报告……"):
                plan = ensure_plan(service, request, draft, inputs)
                completed = service.run(request)
            draft["run_id"] = completed.output_dir.name
            link_plan_run(service, plan, completed)
        except Exception:
            st.error("回测未完成，输入已保留。请检查研究记录中的有效性说明，并重新检查数据后重试。")
    if draft.get("run_id"):
        st.success("回测已完成，研究规则和结果已保存到研究记录。")
        if st.button("查看完整回测报告", key="guided_report"):
            st.session_state["selected_run"] = draft["run_id"]
            st.session_state["backtest_workspace_mode"] = "单次回测"
            st.switch_page("home.py")


def render_pending_backtest(service, request, context=None):
    """Preflight the last submitted form; retry data updates without losing it."""
    signature = repr(request)
    if context is None:
        context = st.session_state.setdefault("pending_plan_context", {})
    render_plan_save(service, request, context, scope="pending")
    state = st.session_state.setdefault("backtest_preflight", {})
    st.write(
        f"待运行方案：{request.strategy_id} · {request.start_date} 至 {request.end_date}"
        f" · 初始资金 {request.initial_cash:,.0f} · 最多 {request.top_n} 只股票"
    )
    st.caption("此处执行最后一次提交的方案。修改上方表单后，请再次点击“检查数据并准备回测”。")
    with st.expander("查看待运行参数"):
        st.json(request.strategy_parameters)
    try:
        refresh = st.button("重新检查数据", key="pending_check")
        if state.get("signature") != signature or refresh:
            state["checks"] = inspect_request(service, request)
            state["signature"] = signature
        checks = state["checks"]
        st.dataframe(checks, hide_index=True, width="stretch")
        ready = checks["状态"].eq("通过").all()
        if not ready:
            st.warning("数据检查未通过。可补齐后重试，已提交方案会保留。")
            if st.button("补齐数据并重新检查", key="pending_update"):
                engine, _ = service.build_engine(request)
                with st.spinner("正在更新行情及基准……"):
                    results = DataCenterService("configs/app.yaml").update_all(
                        engine._warmup_start_date(request.start_date), request.end_date
                    )
                state["checks"] = inspect_request(service, request)
                state["update_failed"] = any(r.status == "FAILED" for r in results)
                st.rerun()
        if state.get("update_failed"):
            st.warning("部分数据更新失败，请检查数据资产中的更新状态；仍可重新尝试。")
        if st.button("运行已检查方案", key="pending_run", type="primary", disabled=not ready):
            state["checks"] = inspect_request(service, request)
            if not state["checks"]["状态"].eq("通过").all():
                st.rerun()
            with st.spinner("正在运行回测……"):
                plan = ensure_plan(service, request, context)
                completed = service.run(request)
            st.session_state["selected_run"] = completed.output_dir.name
            link_plan_run(service, plan, completed)
            st.success("回测完成，可在下方查看结果。")
    except Exception:
        st.error("本次操作未完成，方案已保留。请检查数据资产、风险配置或研究记录后重试。")
