"""Save, restore and compare immutable research plans in the local workspace."""

import json
from copy import deepcopy
from dataclasses import replace
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from quant_platform.application.research_plans import (
    ResearchPlanStore,
    configuration_diff,
    owner_key,
)


def plan_store(service):
    root = service.configs["app"].get("app", {}).get("runtime_dir", "runtime")
    return ResearchPlanStore(Path(root) / "state/research_plans.sqlite3")


def current_owner():
    return owner_key(st.session_state.get("aq_authenticated_user") or "__local__")


def ensure_plan(service, request, context, inputs=None):
    _, snapshot = service.build_engine(request)
    store = plan_store(service)
    plan = store.save(
        current_owner(),
        context.get("plan_title") or request.strategy_id,
        snapshot,
        inputs,
        context.get("plan_id"),
    )
    context["plan_id"] = plan["plan_id"]
    context["plan_revision"] = plan["revision"]
    return plan


def link_plan_run(service, plan, completed):
    plan_store(service).link_run(
        current_owner(), plan, completed.output_dir.name, completed.config_snapshot
    )


def render_plan_save(service, request, context, *, scope, inputs=None):
    with st.expander("保存研究方案", expanded=False):
        st.caption("保存股票池、规则、区间、费用和风控配置。再次修改并保存会新增版本，旧版本保留。")
        title = st.text_input(
            "方案名称",
            value=context.get("plan_title") or request.strategy_id,
            key=scope + "_plan_title",
        )
        context["plan_title"] = title
        if st.button("保存当前版本", key=scope + "_plan_save"):
            try:
                plan = ensure_plan(service, request, context, inputs)
                st.success(f"已保存：{plan['title']} · v{plan['revision']}")
            except (ValueError, OSError):
                st.error("方案未保存，请检查名称和研究配置后重试。")
        st.caption("运行回测时也会自动保存实际执行版本，并关联结果。数据文件本身不会复制。")


def restore_plan(plan):
    st.session_state["restored_plan"] = deepcopy(plan)
    st.session_state["plan_restore_epoch"] = st.session_state.get("plan_restore_epoch", 0) + 1
    st.session_state.pop("backtest_preflight", None)
    st.session_state.pop("pending_plan_title", None)
    for key in list(st.session_state):
        if key.startswith("restored_context_"):
            del st.session_state[key]
    if plan["inputs"].get("idea"):
        draft = deepcopy(plan["inputs"])
        for k in ("start", "end"):
            draft[k] = date.fromisoformat(draft[k])
        draft.update(
            plan_id=plan["plan_id"], plan_revision=plan["revision"], plan_title=plan["title"]
        )
        st.session_state["guided_draft"] = draft
        for key in list(st.session_state):
            if (
                key.startswith("_guided_")
                or key.startswith("guided_confirm_")
                or key.startswith("guided_plan_")
            ):
                del st.session_state[key]
        st.session_state["strategy_workspace_mode"] = "选股想法"
        st.switch_page("app_pages/0_strategy_hub.py")
    else:
        st.session_state["backtest_workspace_mode"] = "方案复用"
        st.switch_page("home.py")


def render_saved_plans(service):
    with st.expander("我的研究方案与版本", expanded=False):
        store = plan_store(service)
        plans = store.list(current_owner())
        st.caption(
            "方案按当前账号隔离，保存在本机；同名方案以编号区分。运行记录仍沿用现有本地记录库。"
        )
        if not plans:
            st.info("暂无保存方案。可以在选股想法或回测提交区保存，也可从历史结果建立方案。")
            return
        labels = [f"{p['title']} · v{p['revision']} · {p['plan_id'][:6]}" for p in plans]
        selected = st.selectbox(
            "选择方案版本", range(len(plans)), format_func=lambda i: labels[i], key="plan_version"
        )
        plan = plans[selected]
        st.caption("保存时间：" + plan["created_at"])
        if st.button("恢复此版本并修改", key="plan_restore"):
            restore_plan(plan)
        linked = store.runs(current_owner(), plan["plan_id"], plan["revision"])
        if linked:
            run_id = st.selectbox("此版本的回测结果", linked, key="plan_linked_run")
            if st.button("打开关联报告", key="plan_open_report"):
                st.session_state["selected_run"] = run_id
                st.session_state["backtest_workspace_mode"] = "单次回测"
                st.switch_page("home.py")
        comparison = st.multiselect(
            "选择2～4个版本比较",
            range(len(plans)),
            format_func=lambda i: labels[i],
            max_selections=4,
            key="plan_compare",
        )
        if len(comparison) < 2:
            return
        chosen = [plans[i] for i in comparison]
        changes = configuration_diff(chosen)
        if changes:
            st.markdown("**哪些条件改了？**")
            st.dataframe(pd.DataFrame(changes), width="stretch", hide_index=True)
        else:
            st.info("这些版本的执行配置相同。")
        scopes = []
        results = []
        for p in chosen:
            config = p["snapshot"]
            bt = config["app"]["backtest"]
            scopes.append(
                json.dumps(
                    {
                        "start": bt["start_date"],
                        "end": bt["end_date"],
                        "benchmark": bt.get("benchmark"),
                        "annualization": bt.get("annualization", 252),
                        "universe": config["universe"],
                        "execution": config["execution"],
                        "initial_cash": bt.get("initial_cash"),
                        "evaluation_mode": bt.get("evaluation_mode"),
                    },
                    sort_keys=True,
                )
            )
            runs = store.runs(current_owner(), p["plan_id"], p["revision"])
            row = {
                "方案": f"{p['title']} · v{p['revision']} · {p['plan_id'][:6]}",
                "区间": f"{bt['start_date']} 至 {bt['end_date']}",
                "结果": "尚未运行",
            }
            if runs:
                try:
                    metrics = service.run_store.load_summary(runs[-1])
                    row.update(
                        {
                            "结果": "已有回测",
                            "累计收益": metrics.get("cumulative_return"),
                            "最大回撤": metrics.get("max_drawdown"),
                            "交易成本": metrics.get("total_transaction_cost"),
                            "审计通过": metrics.get("metrics_reliable", False),
                        }
                    )
                except (OSError, ValueError):
                    row["结果"] = "关联结果不可用"
            results.append(row)
        if len(set(scopes)) > 1:
            st.warning(
                "这些版本的区间、股票池、基准、资金、验证口径或交易费用不同，结果不可直接作为优劣排名。"
            )
        st.dataframe(
            pd.DataFrame(results),
            width="stretch",
            hide_index=True,
            column_config={
                "累计收益": st.column_config.NumberColumn(format="percent"),
                "最大回撤": st.column_config.NumberColumn(format="percent"),
            },
        )
        st.caption("每个版本展示最近关联结果；尚未运行的版本不会填入虚构收益。")


def render_restored_plan(service):
    plan = st.session_state.get("restored_plan")
    if not plan:
        st.info("请从“研究记录 → 我的研究方案与版本”恢复一个方案。")
        return
    service.configs = deepcopy(plan["snapshot"])
    default = service.default_request()
    st.subheader(f"复用方案：{plan['title']} · v{plan['revision']}")
    st.caption("沿用保存的股票池、费用和风控配置；本次重跑作为新的单次研究，需重新进行样本外验证。")
    key = plan["plan_id"] + "_" + str(plan["revision"])
    key += "_" + str(st.session_state.get("plan_restore_epoch", 0))
    with st.form("restore_form_" + key):
        start = st.date_input("研究开始日期", default.start_date)
        end = st.date_input("研究结束日期", default.end_date)
        top_n = st.number_input("最大持仓数量", min_value=1, value=default.top_n)
        cash = st.number_input("初始资金", min_value=1000.0, value=default.initial_cash)
        frequency = st.selectbox(
            "调仓频率",
            ["daily", "weekly", "monthly"],
            index=["daily", "weekly", "monthly"].index(default.rebalance),
        )
        with st.expander("高级规则参数"):
            parameters = st.text_area(
                "策略参数 JSON", json.dumps(default.strategy_parameters, ensure_ascii=False)
            )
            st.json(
                {
                    "股票池": service.configs["universe"],
                    "费用": service.configs["execution"],
                    "风控": service.configs["risk"],
                }
            )
        submitted = st.form_submit_button("检查复用方案")
    context = st.session_state.setdefault(
        "restored_context_" + key, {"plan_id": plan["plan_id"], "plan_title": plan["title"]}
    )
    if submitted:
        try:
            parsed = json.loads(parameters)
            request = replace(
                default,
                start_date=start,
                end_date=end,
                top_n=int(top_n),
                initial_cash=cash,
                rebalance=frequency,
                strategy_parameters=parsed,
            )
            service.build_engine(request)
            context["request"] = request
        except (ValueError, TypeError):
            context.pop("request", None)
            st.error("参数格式或内容无效，请检查后重新提交。")
    if context.get("request"):
        from quant_platform.web.guided_research import render_pending_backtest

        render_pending_backtest(service, context["request"], context=context)
