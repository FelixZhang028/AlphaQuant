"""Task-oriented navigation while retaining every existing tool route."""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True)
class Workspace:
    title: str
    path: str
    icon: str


WORKSPACES = (
    Workspace("首页", "app_pages/15_workspace_home.py", ":material/home:"),
    Workspace("策略研究", "app_pages/17_strategy_research.py", ":material/psychology:"),
    Workspace("我的研究", "app_pages/18_my_research.py", ":material/folder_open:"),
    Workspace("数据与运行", "app_pages/19_data_operations.py", ":material/database:"),
    Workspace("设置", "app_pages/14_settings.py", ":material/settings:"),
)


@dataclass(frozen=True)
class Tool:
    key: str
    title: str
    path: str
    workspace: str
    description: str
    state: tuple[tuple[str, str], ...] = ()


TOOLS = (
    Tool(
        "ai",
        "AI研究员",
        "app_pages/8_agent_lab.py",
        "策略研究",
        "单股分析、多智能体讨论、研究回放与模拟成交",
    ),
    Tool(
        "ideas",
        "选股想法",
        "app_pages/0_strategy_hub.py",
        "策略研究",
        "选择想法、确认选股规则并检查数据",
        (("strategy_workspace_mode", "选股想法"),),
    ),
    Tool(
        "visual",
        "可视化策略",
        "app_pages/0_strategy_hub.py",
        "策略研究",
        "策略模板与规则搭建",
        (("strategy_workspace_mode", "策略搭建"),),
    ),
    Tool(
        "natural",
        "自然语言创建策略",
        "app_pages/0_strategy_hub.py",
        "策略研究",
        "用文字描述选股规则，人工确认后保存",
        (("strategy_workspace_mode", "自然语言"),),
    ),
    Tool(
        "python",
        "Python 策略",
        "app_pages/0_strategy_hub.py",
        "策略研究",
        "自定义策略代码与安全检查",
        (("strategy_workspace_mode", "Python 策略"),),
    ),
    Tool(
        "backtest",
        "单次回测",
        "home.py",
        "策略研究",
        "设置策略、时间与资金",
        (("backtest_workspace_mode", "单次回测"), ("backtest_view", "新建回测")),
    ),
    Tool(
        "validation",
        "参数优化与样本外验证",
        "home.py",
        "策略研究",
        "参数搜索、DSR 校正与滚动验证",
        (("backtest_workspace_mode", "参数优化与稳健性验证"),),
    ),
    Tool(
        "factor", "因子实验室", "app_pages/9_factor_lab.py", "策略研究", "因子分析、组合与策略转换"
    ),
    Tool(
        "knowledge", "先验知识库", "app_pages/12_prior_knowledge.py", "策略研究", "维护 AI 分析依据"
    ),
    Tool(
        "records",
        "研究记录与对比",
        "app_pages/6_run_library.py",
        "我的研究",
        "筛选、导出、对比历史结果",
    ),
    Tool(
        "audit",
        "可信度审计",
        "app_pages/audit_report.py",
        "我的研究",
        "六维评级与证据链",
        (("audit_subject", "平台回测"),),
    ),
    Tool(
        "external",
        "检查外部策略",
        "app_pages/audit_report.py",
        "我的研究",
        "上传报告或成交记录进行核查",
        (("audit_subject", "外部材料"),),
    ),
    Tool(
        "plans",
        "研究方案复用",
        "home.py",
        "我的研究",
        "恢复已保存方案继续研究",
        (("backtest_workspace_mode", "方案复用"),),
    ),
    Tool(
        "data",
        "行情更新",
        "app_pages/1_data_management.py",
        "数据与运行",
        "日常更新与行情维护",
        (("data_update_section", "日常更新"),),
    ),
    Tool(
        "backfill",
        "全市场回填",
        "app_pages/1_data_management.py",
        "数据与运行",
        "创建、查看和停止回填任务",
        (("data_update_section", "全市场回填"),),
    ),
    Tool(
        "jobs",
        "任务记录",
        "app_pages/1_data_management.py",
        "数据与运行",
        "查看执行状态和失败原因",
        (("data_update_section", "任务记录"),),
    ),
    Tool(
        "assets",
        "数据资产",
        "app_pages/13_data_assets.py",
        "数据与运行",
        "数据来源与专项接口",
        (("data_assets_mode", "来源对比"),),
    ),
    Tool(
        "xtick",
        "XTick 接口",
        "app_pages/13_data_assets.py",
        "数据与运行",
        "查询专项行情与金融指标",
        (("data_assets_mode", "XTick 接口"),),
    ),
    Tool(
        "universe", "股票池", "app_pages/5_universe_management.py", "数据与运行", "维护研究股票范围"
    ),
    Tool(
        "risk",
        "风险规则与记录",
        "home.py",
        "数据与运行",
        "仓位、回撤、成交限制与风控记录",
        (("backtest_workspace_mode", "风险规则"),),
    ),
    Tool(
        "settings", "模型与数据源设置", "app_pages/14_settings.py", "设置", "模型、凭证与系统信息"
    ),
    Tool("account", "个人中心", "app_pages/16_user_center.py", "设置", "账号、安全与使用偏好"),
    Tool("welcome", "使用指南", "welcome.py", "设置", "平台介绍与操作引导"),
)

# Embedded/legacy pages remain registered, preserving direct links and bookmarks.
EXTRA_ROUTES = {
    "app_pages/2_research.py": ("参数优化", "策略研究"),
    "app_pages/3_risk_management.py": ("风险管理", "数据与运行"),
    "app_pages/7_strategy_studio.py": ("策略搭建", "策略研究"),
    "app_pages/8_custom_strategy.py": ("自定义策略", "策略研究"),
    "app_pages/10_nl_strategy.py": ("自然语言策略", "策略研究"),
    "app_pages/11_xtick_data.py": ("XTick 数据", "数据与运行"),
    "app_pages/strategy_forensics.py": ("外部材料核查", "我的研究"),
}


def open_tool(key: str) -> None:
    tool = next(item for item in TOOLS if item.key == key)
    for name, value in tool.state:
        st.session_state[name] = value
    st.session_state["workspace_destination"] = tool.path


def open_result(run_id: str) -> None:
    st.session_state["selected_run"] = run_id
    st.session_state["backtest_workspace_mode"] = "单次回测"
    st.session_state["backtest_view"] = "查看结果"
    st.session_state["workspace_destination"] = "home.py"


def tool_button(
    key: str, *, label: str | None = None, primary: bool = False, prefix: str = "workspace"
) -> None:
    tool = next(item for item in TOOLS if item.key == key)
    st.button(
        label or tool.title,
        key=f"{prefix}_{key}",
        on_click=open_tool,
        args=(key,),
        type="primary" if primary else "secondary",
        width="stretch",
    )


def render_directory(*, workspace: str | None = None, prefix: str = "directory") -> None:
    query = (
        st.text_input("查找工具", placeholder="例如：回测、因子、数据源", key=f"{prefix}_search")
        .strip()
        .casefold()
    )
    matches = [
        tool
        for tool in TOOLS
        if (workspace is None or tool.workspace == workspace)
        and query in f"{tool.title} {tool.description} {tool.workspace}".casefold()
    ]
    if not matches:
        st.info("没有匹配的工具，请换一个关键词。")
    for tool in matches:
        tool_button(tool.key, prefix=prefix)
        st.caption(f"{tool.workspace} · {tool.description}")


def build_pages():
    pages = []
    route_workspace = {}
    seen = set()
    for index, workspace in enumerate(WORKSPACES):
        page = st.Page(
            workspace.path, title=workspace.title, icon=workspace.icon, default=index == 0
        )
        pages.append(page)
        seen.add(workspace.path)
    routes = [(tool.path, tool.title, tool.workspace) for tool in TOOLS]
    routes += [(path, title, group) for path, (title, group) in EXTRA_ROUTES.items()]
    for path, title, group in routes:
        if path in seen:
            continue
        page = st.Page(
            path,
            title=title,
            visibility="hidden",
            **({"url_path": "welcome"} if path == "welcome.py" else {}),
        )
        pages.append(page)
        route_workspace[page.url_path] = group
        seen.add(path)
    return {"": pages}, route_workspace


def render_workspace_bar(url_path: str, groups: dict[str, str]) -> None:
    with st.container(horizontal=True):
        group = groups.get(url_path)
        if group:
            workspace = next(item for item in WORKSPACES if item.title == group)
            st.page_link(workspace.path, label=f"返回{group}", icon=":material/arrow_back:")
        with st.popover("全部工具", icon=":material/apps:"):
            render_directory(prefix="all_tools")
