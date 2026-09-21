"""Full-market job controls and persisted history."""

from datetime import date

import pandas as pd
import streamlit as st

from quant_platform.core.diagnostics import redact_text

STATUS = {
    "STARTING": "启动中",
    "RUNNING": "运行中",
    "RETRYING": "等待重试",
    "SUCCESS": "完成",
    "PARTIAL": "部分失败",
    "FAILED": "失败",
    "STOPPED": "已停止",
    "INTERRUPTED": "意外中断",
}
STAGES = {
    "security_master": "证券主表",
    "daily_bars": "日线行情",
    "corporate_actions": "分红送配",
    "universe_membership": "历史股票池",
    "delisting_settlements": "退市结算",
}


@st.fragment(run_every="5s")
def render_jobs(jobs, history=False):
    records = jobs.records()
    active = jobs.active()
    if active:
        st.info("全市场任务正在后台运行，关闭网页不影响执行。")
        progress = active.get("progress", {})
        st.write(
            f"{STATUS[active['status']]} · "
            f"{STAGES.get(progress.get('stage'), '准备数据')} · "
            f"{progress.get('done', 0)} / {progress.get('total', 0)}"
        )
        st.caption(
            f"最近进展：{progress.get('updated_at', '等待首批数据')} · "
            f"本阶段失败：{progress.get('failed', 0)} · 自动重试：{active.get('retries', 0)} 次"
        )
        if progress.get("total"):
            st.progress(min(1.0, progress.get("done", 0) / progress["total"]))
        if active.get("stopping"):
            st.warning("已请求停止，等待当前批次安全结束；数据源卡死时等待看门狗退出。")
        elif st.button("停止任务", key="stop_backfill"):
            jobs.stop(active["id"])
            st.rerun()
    elif not history:
        st.caption("当前没有运行中的全市场任务。")

    if not history:
        st.caption("证券主表始终更新；历史股票池按上市退市规则近似生成，退市结算为推导值。")
        with st.form("full_market_job"):
            start = st.date_input("回填开始日期", date(2015, 1, 1))
            end = st.date_input("回填结束日期", date.today(), max_value=date.today())
            datasets = st.multiselect(
                "回填数据",
                ["bars", "actions", "derived"],
                default=["bars", "actions", "derived"],
                format_func=lambda x: {
                    "bars": "日线行情",
                    "actions": "分红送配",
                    "derived": "历史股票池与退市结算",
                }[x],
            )
            submitted = st.form_submit_button("启动回填", disabled=bool(active), type="primary")
        if submitted:
            try:
                jobs.start(start, end, datasets)
                st.rerun()
            except (ValueError, RuntimeError, OSError) as exc:
                st.error(str(exc))
        st.caption(
            "同一区间会自动跳过已完成部分。改变日期区间会重新抓取；失败后最多自动重试 20 次。"
        )

    if records:
        if history:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "任务": r["id"],
                            "开始日期": r["start_date"],
                            "结束日期": r["end_date"],
                            "状态": STATUS[r["status"]],
                            "创建时间": r["created_at"],
                            "重试次数": r.get("retries", 0),
                        }
                        for r in records
                    ]
                ),
                hide_index=True,
            )
        selected = st.selectbox(
            "查看任务",
            [r["id"] for r in records],
            format_func=lambda x: next(
                f"{r['start_date']} 至 {r['end_date']} · {STATUS[r['status']]} · {x}"
                for r in records
                if r["id"] == x
            ),
        )
        job = next(r for r in records if r["id"] == selected)
        if job["status"] in ("FAILED", "PARTIAL", "STOPPED", "INTERRUPTED"):
            st.warning("任务尚未全部完成，可按原日期和数据范围继续回填。")
            if st.button("继续回填", disabled=bool(active)):
                try:
                    jobs.start(
                        date.fromisoformat(job["start_date"]),
                        date.fromisoformat(job["end_date"]),
                        job["datasets"],
                    )
                    st.rerun()
                except (ValueError, RuntimeError, OSError) as exc:
                    st.error(str(exc))
        with st.expander("最近日志（最多 32 KB）"):
            st.code(redact_text(jobs.log(selected)) or "暂无日志", language=None)
    elif history:
        st.info("暂无后台回填任务记录。命令行任务的数据版本仍可在日常更新中查看。")
