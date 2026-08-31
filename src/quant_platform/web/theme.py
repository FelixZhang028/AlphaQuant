"""全局 UI 主题：模仿 DeepSeek Harness 的深色中性蓝设计语言（纯 CSS）。

``inject_global_css()`` 由 ``app.py`` 入口注入一次，对所有页面生效；
样式不侵入 ``web/agent_trace.py`` 的 ``.aq-*`` 作用域。

设计 tokens 取自 DeepSeek Harness 前端源码（dark theme）：
- 背景层：base #151517 / layer1 #232324 / layer2 #2c2c2e / layer3 #353638
- 边框：rgba(255,255,255,.06 ~ .16)，hover 交互 rgba(255,255,255,.08/.14)
- 文字：primary #f9fafb / secondary #cfd3d6 / tertiary #adb2b8 / caption #81858c
- 品牌蓝：#5686fe（450），#679efe（400），#4176e6（500）
- 状态色：success #22c55e / warn #f59e0b / error #f25a5a
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

_GLOBAL_CSS = """
<style>
/* ================= 基础画布 ================= */
html, body, [data-testid="stAppViewContainer"] {
    background: #151517;
    color: #cfd3d6;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
        "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei",
        "Helvetica Neue", Arial, sans-serif;
}

/* 顶部品牌微光：克制、低对比 */
.stApp::before {
    content: "";
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    height: 160px;
    pointer-events: none;
    z-index: 0;
    background: radial-gradient(120% 100% at 50% 0%,
        rgba(86, 134, 254, 0.10) 0%,
        rgba(86, 134, 254, 0.03) 45%,
        transparent 100%);
}

/* ================= 文字层级 ================= */
h1, h2, h3 { color: #f9fafb; letter-spacing: -0.01em; }
h1 { font-weight: 650; }
p, li, label { color: #cfd3d6; }

/* ================= 页面进入动画 ================= */
[data-testid="stMainBlockContainer"] {
    animation: aqFadeUp 0.35s ease-out;
    /* 去除 Streamlit 默认容器顶部 gap：整个平台内容贴齐视口顶端 */
    padding-top: 0;
}

/* ================= 去除 Streamlit 默认顶部装饰 =================
   顶栏保留但透明化：原生的侧栏收起/展开控件挂在 stHeader 内
   （1.62 中收起态是 stExpandSidebarButton，展开态是 stSidebarCollapseButton），
   若整体 display:none 会导致侧栏收起后无法再次展开。
   因此仅隐藏装饰条与工具栏，header 本体透明 + 穿透点击，
   再把原生控件单独恢复可点击。 */
[data-testid="stAppViewContainer"] [data-testid="stHeader"] {
    background: transparent;
    pointer-events: none;
}
/* 注意：收起态的「»」展开按钮（stExpandSidebarButton）在 stToolbar 内部，
   不能把 stToolbar 整体 display:none——只隐藏右侧动作区与装饰条，
   stToolbar 本体设为穿透点击，再单独恢复展开按钮可点击。 */
[data-testid="stAppViewContainer"] [data-testid="stDecoration"],
[data-testid="stAppViewContainer"] [data-testid="stToolbarActions"],
[data-testid="stAppViewContainer"] [data-testid="stHeaderActionElements"] {
    display: none;
}
[data-testid="stAppViewContainer"] [data-testid="stToolbar"] {
    pointer-events: none;
    background: transparent;
}
/* 原生侧栏控件恢复可点击并主题化（同时兼容新旧 testid） */
[data-testid="stAppViewContainer"] [data-testid="stHeader"] button,
[data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarCollapsedControl"] button,
[data-testid="stSidebarCollapsedControl"] *,
[data-testid="stExpandSidebarButton"],
[data-testid="stExpandSidebarButton"] * {
    pointer-events: auto;
}
/* Streamlit 默认只在侧栏 hover 时才显示「«」收起按钮
   （stSidebarCollapseButton 平时 visibility:hidden），这里强制常显 */
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapseButton"] button {
    visibility: visible !important;
}
[data-testid="stSidebarCollapsedControl"] button,
[data-testid="stSidebarCollapseButton"] button,
button[data-testid="stExpandSidebarButton"] {
    width: 2.3rem;
    height: 2.3rem;
    min-width: 2.3rem;
    border: 1px solid rgba(126, 200, 255, 0.28);
    border-radius: 0.65rem;
    background: rgba(10, 20, 38, 0.92);
    color: #eaf3ff;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.32);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    transition: background 0.18s ease, border-color 0.18s ease;
}
[data-testid="stSidebarCollapsedControl"] button:hover,
[data-testid="stSidebarCollapseButton"] button:hover,
button[data-testid="stExpandSidebarButton"]:hover {
    background: rgba(28, 48, 84, 0.96);
    border-color: rgba(126, 200, 255, 0.85);
}
[data-testid="stSidebarCollapsedControl"] button *,
[data-testid="stSidebarCollapseButton"] button *,
button[data-testid="stExpandSidebarButton"] * {
    color: #eaf3ff;
    fill: #eaf3ff;
}
[data-testid="stAppViewContainer"] [data-testid="stMain"] {
    margin-top: 0;
    padding-top: 0;
}
@keyframes aqFadeUp {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}

/* ================= 卡片 / 指标 / 表单：Harness layer-1 ================= */
[data-testid="stMetric"],
[data-testid="stExpander"],
[data-testid="stForm"],
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {
    background: #232324;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    transition: border-color 0.18s ease, background 0.18s ease;
}
[data-testid="stMetric"] { padding: 0.6rem 0.9rem; }
[data-testid="stMetric"]:hover,
[data-testid="stExpander"]:hover,
[data-testid="stForm"]:hover {
    border-color: rgba(255, 255, 255, 0.16);
    background: #2a2a2c;
}
[data-testid="stMetricValue"] {
    color: #f9fafb;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
[data-testid="stMetricLabel"] { color: #81858c; }

/* ================= 按钮：Harness pill ================= */
button[kind="primary"],
[data-testid="stFormSubmitButton"] button[kind="primary"] {
    background: #f9fafb;
    color: #0f1115;
    border: none;
    border-radius: 18px;
    font-weight: 600;
    transition: background 0.18s ease;
}
/* 白底按钮内的文字统一为黑色：全局 `p, li, label` 浅灰规则会盖过
   按钮继承色，必须显式覆盖内部元素 */
button[kind="primary"] p,
button[kind="primary"] span,
button[kind="primary"] div,
[data-testid="stFormSubmitButton"] button[kind="primary"] p,
[data-testid="stFormSubmitButton"] button[kind="primary"] span,
[data-testid="stFormSubmitButton"] button[kind="primary"] div {
    color: #0f1115;
}
button[kind="primary"]:hover {
    background: #e6e8ec;
    box-shadow: none;
}
[data-testid="stBaseButton-secondary"],
button[kind="secondary"] {
    background: transparent;
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 18px;
    color: #cfd3d6;
    transition: background 0.18s ease, border-color 0.18s ease;
}
[data-testid="stBaseButton-secondary"]:hover,
button[kind="secondary"]:hover {
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.24);
}

/* ================= 输入框 ================= */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stDateInput"] input,
[data-testid="stTimeInput"] input {
    background: #232324;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 10px;
    color: #f9fafb;
    transition: border-color 0.18s ease, box-shadow 0.18s ease;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color: #5686fe;
    box-shadow: 0 0 0 3px rgba(86, 134, 254, 0.18);
}
[data-testid="stSelectbox"] > div > div,
[data-testid="stMultiSelect"] > div > div {
    background: #232324;
    border-color: rgba(255, 255, 255, 0.12);
    border-radius: 10px;
    color: #f9fafb;
}

/* ================= Tabs ================= */
[data-testid="stTabs"] [role="tab"] { color: #adb2b8; }
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #f9fafb;
    border-bottom: 2px solid #5686fe;
}

/* ================= Sidebar：Harness #1b1b1c ================= */
[data-testid="stSidebar"] {
    background: #1b1b1c;
    border-right: 1px solid rgba(255, 255, 255, 0.06);
}
/* 隐藏「开始」分组（落地/登录首页入口）：welcome.py 仍是默认首页，
   但正式版不在侧栏导航中展示该入口 */
[data-testid="stSidebarNavItems"] > div:first-child {
    display: none !important;
}
[data-testid="stSidebar"] a[aria-current="page"],
[data-testid="stSidebar"] .stNavigation [aria-selected="true"] {
    background: rgba(255, 255, 255, 0.06);
    border-left: 3px solid #5686fe;
    border-radius: 0 8px 8px 0;
}

/* ================= 滚动条 ================= */
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
    background: #545557;
    border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover { background: #65676b; }

/* ================= 动效降级 ================= */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation: none !important;
        transition: none !important;
    }
}
</style>
"""

_WORKBENCH_CSS = """
<style>
/* FellowQuant 工作台：与 Welcome 主页共用深蓝、青绿色和玻璃面板语言。
   Welcome 页存在 .aq-launch-splash 时不应用这组规则。 */
html:not(:has(.aq-launch-splash)),
html:not(:has(.aq-launch-splash)) body,
html:not(:has(.aq-launch-splash)) [data-testid="stAppViewContainer"] {
    background:
        radial-gradient(72rem 34rem at 78% -8%, rgba(32,113,126,.22), transparent 63%),
        radial-gradient(48rem 28rem at 18% 20%, rgba(255,180,84,.08), transparent 70%),
        #04060e !important;
    color: #f5f7f8;
}
html:not(:has(.aq-launch-splash)) [data-testid="stMainBlockContainer"] {
    width: min(1180px, calc(100vw - 2rem)) !important;
    max-width: 1180px !important;
    margin: 0 auto !important;
    padding: clamp(3rem, 6vw, 5.5rem) clamp(1rem, 3vw, 2.25rem) 5rem !important;
}
html:not(:has(.aq-launch-splash)) [data-testid="stMainBlockContainer"] > div {
    gap: 1.05rem !important;
}
html:not(:has(.aq-launch-splash)) h1 {
    margin: 0 0 .45rem !important;
    color: #f5f7f8 !important;
    font-size: clamp(2.35rem, 4.4vw, 4.2rem) !important;
    font-weight: 650 !important;
    letter-spacing: -.055em !important;
    line-height: .98 !important;
    text-shadow: 0 0 34px rgba(126,200,255,.10);
}
html:not(:has(.aq-launch-splash)) h1::after {
    content: "";
    display: block;
    width: 4.2rem;
    height: 2px;
    margin-top: 1rem;
    background: linear-gradient(90deg, #7ec8ff, transparent);
}
html:not(:has(.aq-launch-splash)) h2,
html:not(:has(.aq-launch-splash)) h3 {
    color: #f5f7f8 !important;
    letter-spacing: -.025em !important;
}
html:not(:has(.aq-launch-splash)) h2 {
    margin-top: 2.5rem !important;
    font-size: clamp(1.75rem, 3vw, 2.65rem) !important;
}
html:not(:has(.aq-launch-splash)) [data-testid="stCaptionContainer"] {
    color: #98b0c2 !important;
    font-size: .86rem !important;
}

html:not(:has(.aq-launch-splash)) [data-testid="stExpander"],
html:not(:has(.aq-launch-splash)) [data-testid="stForm"] {
    background: linear-gradient(135deg, rgba(20,39,50,.86), rgba(8,18,27,.88)) !important;
    border: 1px solid rgba(126,200,255,.18) !important;
    border-radius: 16px !important;
    box-shadow: 0 20px 58px rgba(0,0,0,.20), inset 0 1px 0 rgba(255,255,255,.05) !important;
}
html:not(:has(.aq-launch-splash)) [data-testid="stExpander"] summary {
    color: #f5f7f8 !important;
    font-weight: 600 !important;
}
html:not(:has(.aq-launch-splash)) [data-testid="stExpander"] summary:hover {
    color: #7ec8ff !important;
}
html:not(:has(.aq-launch-splash)) [data-testid="stForm"] {
    background: rgba(255,255,255,.025) !important;
    border-color: rgba(255,255,255,.09) !important;
    border-radius: 14px !important;
}

html:not(:has(.aq-launch-splash)) label,
html:not(:has(.aq-launch-splash)) [data-testid="stWidgetLabel"] p {
    color: #b8c9d8 !important;
    font-size: .82rem !important;
    font-weight: 550 !important;
}
html:not(:has(.aq-launch-splash)) input,
html:not(:has(.aq-launch-splash)) textarea,
html:not(:has(.aq-launch-splash)) [data-baseweb="select"] > div {
    background: rgba(5,13,19,.46) !important;
    border-color: rgba(126,200,255,.16) !important;
    border-radius: 10px !important;
    color: #f5f7f8 !important;
    transition: border-color .2s ease, box-shadow .2s ease, background .2s ease !important;
}
html:not(:has(.aq-launch-splash)) input:focus,
html:not(:has(.aq-launch-splash)) textarea:focus,
html:not(:has(.aq-launch-splash)) [data-baseweb="select"] > div:focus-within {
    background: rgba(9,29,37,.72) !important;
    border-color: #7ec8ff !important;
    box-shadow: 0 0 0 3px rgba(126,200,255,.12), 0 0 24px rgba(126,200,255,.08) !important;
}
html:not(:has(.aq-launch-splash)) input::placeholder,
html:not(:has(.aq-launch-splash)) textarea::placeholder {
    color: #68809a !important;
}

html:not(:has(.aq-launch-splash)) [data-testid="stMetric"] {
    min-height: 6rem;
    padding: 1rem 1.1rem !important;
    background: linear-gradient(145deg, rgba(19,42,53,.86), rgba(7,18,27,.82)) !important;
    border: 1px solid rgba(126,200,255,.13) !important;
    border-radius: 14px !important;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.04), 0 12px 30px rgba(0,0,0,.14) !important;
    transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease !important;
}
html:not(:has(.aq-launch-splash)) [data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    border-color: rgba(126,200,255,.42) !important;
    box-shadow: 0 16px 34px rgba(0,0,0,.24), 0 0 24px rgba(126,200,255,.07) !important;
}
html:not(:has(.aq-launch-splash)) [data-testid="stMetricLabel"] { color: #98b0c2 !important; }
html:not(:has(.aq-launch-splash)) [data-testid="stMetricValue"] {
    color: #f5f7f8 !important;
    font-size: clamp(1.2rem, 2vw, 1.7rem) !important;
}

html:not(:has(.aq-launch-splash)) [data-testid="stTabs"] {
    margin-top: 1.5rem;
    padding: .4rem;
    background: rgba(6,15,22,.58);
    border: 1px solid rgba(126,200,255,.12);
    border-radius: 14px;
}
html:not(:has(.aq-launch-splash)) [data-testid="stTabs"] [role="tab"] {
    min-height: 2.45rem;
    padding: 0 .95rem;
    border-radius: 9px;
    color: #8ca3b8 !important;
    transition: color .2s ease, background .2s ease, transform .2s ease;
}
html:not(:has(.aq-launch-splash)) [data-testid="stTabs"] [role="tab"]:hover {
    color: #f5f7f8 !important;
    background: rgba(126,200,255,.07);
}
html:not(:has(.aq-launch-splash)) [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #061116 !important;
    background: #7ec8ff !important;
    border: 0 !important;
}
/* 选中 Tab 为浅底，其内部文字节点也必须是深色，否则被全局 p 规则压成浅色 */
html:not(:has(.aq-launch-splash)) [data-testid="stTabs"] [role="tab"][aria-selected="true"] * {
    color: #061116 !important;
}
html:not(:has(.aq-launch-splash)) [data-testid="stTabs"] [data-baseweb="tab-highlight"] {
    display: none !important;
}

html:not(:has(.aq-launch-splash)) [data-testid="stAlert"] {
    border-radius: 12px !important;
    background: rgba(126,200,255,.07) !important;
    border: 1px solid rgba(126,200,255,.22) !important;
}
html:not(:has(.aq-launch-splash)) [data-testid="stDataFrame"] {
    overflow: hidden;
    border: 1px solid rgba(126,200,255,.15) !important;
    border-radius: 14px !important;
    box-shadow: 0 16px 38px rgba(0,0,0,.16) !important;
}
html:not(:has(.aq-launch-splash)) [data-testid="stVegaLiteChart"],
html:not(:has(.aq-launch-splash)) [data-testid="stArrowVegaLiteChart"] {
    padding: .45rem;
    background: rgba(7,19,27,.52);
    border: 1px solid rgba(126,200,255,.12);
    border-radius: 14px;
}
html:not(:has(.aq-launch-splash)) hr {
    margin: 2rem 0 !important;
    border-color: rgba(126,200,255,.13) !important;
}

html:not(:has(.aq-launch-splash)) button {
    transition: transform .2s cubic-bezier(.22,1,.36,1), box-shadow .2s ease,
                border-color .2s ease, background .2s ease !important;
}
html:not(:has(.aq-launch-splash)) button:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 24px rgba(0,0,0,.22) !important;
}
html:not(:has(.aq-launch-splash)) button[kind="primary"],
html:not(:has(.aq-launch-splash)) button[kind="primaryFormSubmit"],
html:not(:has(.aq-launch-splash)) [data-testid="stBaseButton-primary"],
html:not(:has(.aq-launch-splash)) [data-testid="stBaseButton-primaryFormSubmit"] {
    background: linear-gradient(135deg, #7ec8ff, #3b82f6) !important;
    color: #071116 !important;
    border: 0 !important;
    border-radius: 10px !important;
    box-shadow: 0 8px 22px rgba(59,130,246,.22) !important;
}
/* 浅色按钮必须配深色文字：按钮文字实际渲染在内部 p/span/div 上，
   需逐个压住全局 p { color:#cfd3d6 } 规则 */
html:not(:has(.aq-launch-splash)) button[kind="primary"] *,
html:not(:has(.aq-launch-splash)) button[kind="primaryFormSubmit"] *,
html:not(:has(.aq-launch-splash)) [data-testid="stBaseButton-primary"] *,
html:not(:has(.aq-launch-splash)) [data-testid="stBaseButton-primaryFormSubmit"] * {
    color: #071116 !important;
}
html:not(:has(.aq-launch-splash)) button[kind="secondary"],
html:not(:has(.aq-launch-splash)) button[kind="secondaryFormSubmit"] {
    border-color: rgba(126,200,255,.24) !important;
    border-radius: 10px !important;
}
html:not(:has(.aq-launch-splash)) button[kind="secondary"]:hover,
html:not(:has(.aq-launch-splash)) button[kind="secondaryFormSubmit"]:hover {
    background: rgba(126,200,255,.09) !important;
    border-color: rgba(126,200,255,.55) !important;
}

@media (max-width: 800px) {
    html:not(:has(.aq-launch-splash)) [data-testid="stMainBlockContainer"] {
        width: 100% !important;
        padding: 3rem 1rem 3.5rem !important;
    }
    html:not(:has(.aq-launch-splash)) h1 { font-size: 2.35rem !important; }
    html:not(:has(.aq-launch-splash)) [data-testid="stTabs"] [role="tab"] {
        padding: 0 .55rem;
        font-size: .82rem;
    }
}
</style>
"""

_LANDING_CSS = """
<style>
/* ============ 顶部品牌条 ============ */
.aq-topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.4rem 0 1.2rem;
    animation: aqFadeUp 0.4s ease-out both;
}
.aq-brand {
    display: flex;
    align-items: center;
    gap: 0.7rem;
}
.aq-brand-logo {
    width: 30px;
    height: 30px;
    border-radius: 8px;
    object-fit: cover;
}
.aq-wordmark {
    font-size: 16px;
    line-height: 24px;
    font-weight: 600;
    letter-spacing: 0.08em;
    color: #f9fafb;
}
.aq-topbar-pills {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
}

/* ============ Pill 徽章 ============ */
.aq-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    height: 26px;
    padding: 0 12px;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 13px;
    background: #232324;
    color: #adb2b8;
    font-size: 12px;
    line-height: 18px;
    white-space: nowrap;
}
.aq-pill-ok {
    color: #4ed17e;
    border-color: rgba(78, 209, 126, 0.30);
    background: rgba(34, 197, 94, 0.08);
}
.aq-pill-warn {
    color: #f7ad31;
    border-color: rgba(245, 158, 11, 0.30);
    background: rgba(245, 158, 11, 0.08);
}
.aq-pill-err {
    color: #f25a5a;
    border-color: rgba(242, 90, 90, 0.30);
    background: rgba(242, 90, 90, 0.08);
}

/* ============ Hero（Typora feature 风格：研究优势 + 固定 Mac 编辑器） ============ */
.aq-hero {
    position: relative;
    text-align: left;
    margin: 0.3rem 0 0.8rem;
    padding: 4.2rem 3rem 7.2rem;
    min-height: 560px;
    border-radius: 20px;
    overflow: hidden;
    background: linear-gradient(155deg, #0d2146 0%, #0a1730 46%, #060b18 100%);
    border: 1px solid rgba(130, 160, 230, 0.14);
    animation: aqFadeUp 0.5s ease-out both;
}
/* 两条流动光绸 */
.aq-hero::before,
.aq-hero::after {
    content: "";
    position: absolute;
    width: 135%;
    height: 58%;
    left: -18%;
    border-radius: 50%;
    filter: blur(48px);
    pointer-events: none;
}
.aq-hero::before {
    top: -24%;
    background: linear-gradient(
        100deg,
        transparent 8%,
        rgba(150, 180, 255, 0.32) 34%,
        rgba(196, 210, 255, 0.42) 52%,
        rgba(140, 170, 250, 0.28) 68%,
        transparent 92%
    );
    transform: rotate(-7deg);
    animation: aqSilkA 13s ease-in-out infinite alternate;
}
.aq-hero::after {
    bottom: -30%;
    background: linear-gradient(
        100deg,
        transparent 10%,
        rgba(118, 148, 240, 0.26) 38%,
        rgba(172, 192, 255, 0.34) 56%,
        transparent 90%
    );
    transform: rotate(5deg);
    animation: aqSilkB 17s ease-in-out infinite alternate;
}
@keyframes aqSilkA {
    from { transform: rotate(-7deg) translateX(-4%); }
    to { transform: rotate(-5deg) translateX(4%); }
}
@keyframes aqSilkB {
    from { transform: rotate(5deg) translateX(3%); }
    to { transform: rotate(7deg) translateX(-4%); }
}
.aq-hero-grid {
    position: relative;
    display: grid;
    grid-template-columns: 1.25fr 1fr;
    gap: 2.4rem;
    align-items: center;
}
@media (max-width: 1100px) {
    .aq-hero-grid { grid-template-columns: 1fr; }
    .aq-term { display: none; }
}
/* ============ Hero 底部向下滚动指示（毛玻璃胶囊 + 上下浮动） ============ */
.aq-scroll-hint {
    position: absolute;
    left: 50%;
    bottom: 1.4rem;
    transform: translateX(-50%);
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0.34rem 0.95rem;
    border-radius: 999px;
    background: rgba(16, 24, 42, 0.55);
    border: 1px solid rgba(255, 255, 255, 0.14);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    color: #b9c6e4;
    font-size: 0.78rem;
    letter-spacing: 0.06em;
    white-space: nowrap;
    animation: aqScrollHintFloat 2.2s ease-in-out infinite;
    pointer-events: none;
    z-index: 2;
}
.aq-scroll-hint svg {
    width: 13px;
    height: 13px;
    fill: none;
    stroke: currentColor;
    stroke-width: 2;
    animation: aqScrollHintNudge 2.2s ease-in-out infinite;
}
@keyframes aqScrollHintFloat {
    0%, 100% { transform: translateX(-50%) translateY(0); opacity: 0.85; }
    50% { transform: translateX(-50%) translateY(-6px); opacity: 1; }
}
@keyframes aqScrollHintNudge {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(2px); }
}
.aq-hero-eyebrow {
    font-size: 0.95rem;
    font-weight: 600;
    color: #c6d4f2;
    letter-spacing: 0.02em;
    margin-bottom: 0.4rem;
    animation: aqFadeUp 0.5s ease-out 0.05s both;
}
.aq-hero-badge {
    display: inline-block;
    padding: 0.24rem 0.9rem;
    border: 1px solid rgba(150, 180, 255, 0.35);
    border-radius: 999px;
    background: rgba(86, 134, 254, 0.14);
    color: #b9ccff;
    font-size: 0.8rem;
    letter-spacing: 0.06em;
    backdrop-filter: blur(4px);
    animation: aqFadeUp 0.5s ease-out 0.05s both;
}
.aq-hero-title {
    font-size: 3rem;
    font-weight: 700;
    letter-spacing: -0.03em;
    line-height: 1.18;
    margin: 1.1rem 0 0.7rem;
    color: #f4f7ff;
    text-shadow: 0 2px 30px rgba(90, 130, 250, 0.35);
    word-break: keep-all;
    overflow-wrap: normal;
    animation: aqFadeUp 0.55s ease-out 0.14s both;
}
.aq-hero-title .aq-accent {
    background: linear-gradient(92deg, #7ea8ff 0%, #a9c3ff 55%, #6fd6e8 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
}
.aq-hero-sub {
    color: #a5b1c8;
    font-size: 1.05rem;
    max-width: 560px;
    margin: 0;
    line-height: 1.8;
    animation: aqFadeUp 0.55s ease-out 0.24s both;
}

/* 悬浮终端卡 */
.aq-term {
    position: relative;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 14px;
    background: rgba(9, 13, 24, 0.82);
    box-shadow: 0 24px 60px rgba(0, 0, 0, 0.5);
    backdrop-filter: blur(8px);
    overflow: hidden;
    animation: aqFadeUp 0.6s ease-out 0.3s both;
}
@keyframes aqFloatY {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-8px); }
}
.aq-term-bar {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 0.65rem 0.9rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.07);
    background: rgba(255, 255, 255, 0.03);
}
.aq-term-dot { width: 11px; height: 11px; border-radius: 50%; }
.aq-term-dot.r { background: #f25a5a; }
.aq-term-dot.y { background: #f7ad31; }
.aq-term-dot.g { background: #4ed17e; }
.aq-term-title {
    margin-left: 0.5rem;
    color: #81858c;
    font-size: 0.75rem;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.aq-term-body {
    padding: 0.95rem 1.1rem 1.1rem;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.84rem;
    line-height: 1.95;
    color: #c9d4e8;
    white-space: pre-wrap;
}
.aq-term-prompt { color: #679efe; }
.aq-term-ok { color: #4ed17e; }
.aq-term-dim { color: #6b7280; }
.aq-cursor {
    display: inline-block;
    width: 8px;
    height: 1.05em;
    vertical-align: text-bottom;
    background: #7ea8ff;
    animation: aqBlink 1.1s steps(1) infinite;
}
@keyframes aqBlink { 50% { opacity: 0; } }

/* Typora-like feature hero: the window stays still; only its editor note changes. */
.st-key-aq_hero_wrap .aq-hero {
    min-height: 100svh;
    height: 100svh;
    display: flex;
    align-items: center;
    padding: 5rem clamp(1.5rem, 8vw, 8rem) 4rem;
    margin: 0;
    border-radius: 0 !important;
}
.st-key-aq_hero_wrap .aq-hero-grid {
    width: min(1160px, 100%);
    margin: 0 auto;
    grid-template-columns: minmax(0, .88fr) minmax(420px, 1fr);
    gap: clamp(3rem, 7vw, 7.5rem);
    align-items: center;
}
.st-key-aq_hero_wrap .aq-hero-grid > div:first-child {
    max-width: 500px;
}
.aq-hero-title {
    font-size: clamp(2.6rem, 4.5vw, 5rem);
    line-height: 1.04;
    letter-spacing: -.065em;
    margin: 1.25rem 0 1rem;
}
.aq-hero-title .aq-accent {
    font-family: "Space Grotesk", sans-serif;
    font-weight: 700;
    letter-spacing: -.065em;
}
.aq-hero-sub {
    max-width: 500px;
    color: #a8b8c8;
    font-size: clamp(.95rem, 1.15vw, 1.08rem);
    line-height: 1.78;
}
.aq-hero-highlights {
    display: grid;
    gap: .9rem;
    margin-top: 2.1rem;
}
.aq-hero-highlight {
    display: flex;
    align-items: center;
    gap: .8rem;
    color: #edf5f3;
    font-size: clamp(.92rem, 1.1vw, 1rem);
    animation: aqFadeUp .55s ease-out both;
}
.aq-hero-highlight:nth-child(2) { animation-delay: .08s; }
.aq-hero-highlight:nth-child(3) { animation-delay: .16s; }
.aq-highlight-icon {
    display: inline-grid;
    place-items: center;
    width: 1.55rem;
    height: 1.55rem;
    border: 1px solid rgba(126,200,255,.38);
    border-radius: 50%;
    color: #7ec8ff;
    font-size: .86rem;
    line-height: 1;
    transition: transform .25s ease, background .25s ease, border-color .25s ease;
}
.aq-hero-highlight:hover .aq-highlight-icon {
    transform: rotate(12deg) scale(1.12);
    background: rgba(126,200,255,.12);
    border-color: #7ec8ff;
}
.st-key-aq_hero_wrap .aq-hero-badge { margin-top: .5rem; }
.aq-term {
    width: min(100%, 600px);
    min-height: 420px;
    height: 420px;
    margin: 0;
    transform: none !important;
    border-radius: 14px;
    background: linear-gradient(145deg, rgba(18,31,38,.98), rgba(5,12,17,.98));
    border-color: rgba(126,200,255,.28);
    box-shadow: 0 24px 80px rgba(0,0,0,.48), 0 0 0 1px rgba(126,200,255,.06) inset;
}
.aq-term-bar {
    height: 42px;
    box-sizing: border-box;
    padding: 0 .9rem;
    background: linear-gradient(180deg, #1a2a44, #101c33);
    border-bottom-color: rgba(126,200,255,.16);
}
.aq-term-title { color: #a8b8c8; }
.aq-term-body {
    position: relative;
    height: 378px;
    box-sizing: border-box;
    padding: 0 !important;
    overflow: hidden;
    background: radial-gradient(circle at 76% 18%, rgba(126,200,255,.08), transparent 30%), #0a1424;
    color: #b9c8ca;
    font-family: Georgia, "Times New Roman", serif;
    font-size: 1rem;
    line-height: 1.65;
    white-space: normal;
}
.aq-term-scene {
    position: absolute;
    inset: 0;
    padding: 2rem 2rem 2.4rem;
    box-sizing: border-box;
    opacity: 0;
    transform: translateY(12px);
    clip-path: inset(0 100% 0 0);
    animation: aqTermScene 16s ease-in-out infinite;
}
.aq-term-scene:nth-child(2) { animation-delay: 5.3s; }
.aq-term-scene:nth-child(3) { animation-delay: 10.6s; }
.aq-editor-heading {
    margin: 0 0 1.3rem;
    color: #f2f7f5;
    font: 600 clamp(1.55rem, 2.3vw, 2rem)/1.12 Georgia, "Times New Roman", serif;
    letter-spacing: -.025em;
}
.aq-editor-copy { margin: 0 0 1rem; color: #acc0d2; }
.aq-editor-list { margin: 0; padding-left: 1.2rem; color: #acc0d2; }
.aq-editor-list li { margin: .55rem 0; }
.aq-editor-list strong { color: #7ec8ff; }
.aq-term-line { margin: 0; }
.aq-term-scene .aq-cursor { background: #7ec8ff; }
@keyframes aqTermScene {
    0%, 7% {
        opacity: 0;
        transform: translateY(12px);
        clip-path: inset(0 100% 0 0);
    }
    10% {
        opacity: 1;
        transform: translateY(0);
        clip-path: inset(0 92% 0 0);
    }
    24%, 31% {
        opacity: 1;
        transform: translateY(0);
        clip-path: inset(0 0 0 0);
    }
    38%, 100% {
        opacity: 0;
        transform: translateY(-8px);
        clip-path: inset(0 0 0 0);
    }
}
.aq-scroll-hint, .st-key-aq_hero_ctas { display: none !important; }

/* ============ 启动器（仿 Harness 输入框，落地页唯一表单） ============ */
[data-testid="stForm"] {
    max-width: 860px;
    margin: 1.6rem auto 0;
    background: #232324;
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 16px;
    padding: 0.55rem 0.55rem 0.55rem 1rem;
    transition: border-color 0.18s ease, box-shadow 0.18s ease;
}
[data-testid="stForm"]:focus-within {
    border-color: #5686fe;
    box-shadow: 0 0 0 3px rgba(86, 134, 254, 0.16);
}
[data-testid="stForm"] [data-testid="stTextInput"] {
    display: flex;
    align-items: center;
    height: 100%;
}
[data-testid="stForm"] [data-testid="stTextInput"] input {
    background: transparent;
    border: none;
    box-shadow: none !important;
    border-radius: 0;
    font-size: 1.02rem;
    padding: 0.5rem 0.2rem;
}
[data-testid="stForm"] [data-testid="stTextInput"] input:focus {
    box-shadow: none !important;
}

/* ============ 特性 chips ============ */
.aq-hero-chips {
    margin-top: 1.3rem;
    display: flex;
    gap: 0.55rem;
    justify-content: center;
    flex-wrap: wrap;
    animation: aqFadeUp 0.55s ease-out 0.32s both;
}
.aq-hero-chip {
    padding: 0.28rem 0.9rem;
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.03);
    color: #adb2b8;
    font-size: 0.8rem;
    transition: border-color 0.2s ease, color 0.2s ease;
}
.aq-hero-chip:hover {
    border-color: rgba(103, 158, 254, 0.55);
    color: #f9fafb;
}

/* ============ 区块标题 ============ */
.aq-section {
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    margin: 2rem 0 0.9rem;
}
.aq-section-title {
    font-size: 1.05rem;
    font-weight: 600;
    color: #f9fafb;
    letter-spacing: 0.01em;
}
.aq-section-hint {
    font-size: 0.82rem;
    color: #81858c;
}

/* ============ 模块卡（Harness session card） ============ */
.aq-module-card {
    height: 100%;
    display: flex;
    flex-direction: column;
    padding: 1.15rem 1.15rem 1rem;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    background: #232324;
    transition: border-color 0.2s ease, transform 0.2s ease, background 0.2s ease;
    animation: aqFadeUp 0.5s ease-out both;
}
.aq-module-card:hover {
    transform: translateY(-2px);
    border-color: rgba(255, 255, 255, 0.18);
    background: #2a2a2c;
}
.aq-module-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.65rem;
}
.aq-module-icon {
    width: 34px;
    height: 34px;
    border-radius: 9px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: rgba(86, 134, 254, 0.12);
    color: #679efe;
    font-family: "Material Symbols Rounded";
    font-size: 20px;
    line-height: 1;
    font-feature-settings: "liga";
    font-variation-settings: "FILL" 0, "wght" 400, "GRAD" 0, "opsz" 24;
}
.aq-module-title {
    font-size: 1rem;
    font-weight: 600;
    color: #f9fafb;
    margin: 0 0 0.3rem;
}
.aq-module-desc {
    color: #adb2b8;
    font-size: 0.86rem;
    line-height: 1.6;
    margin: 0;
    flex: 1;
}
.aq-module-footer {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    margin-top: 0.8rem;
    color: #81858c;
    font-size: 0.78rem;
}

/* ============ 状态圆点（仿 Harness _dot） ============ */
.aq-dot {
    position: relative;
    display: inline-block;
    flex: none;
    width: 9px;
    height: 9px;
}
.aq-dot::before {
    content: "";
    position: absolute;
    top: 0; right: 0; bottom: 0; left: 0;
    border-radius: 50%;
    background: currentColor;
    opacity: 0.14;
}
.aq-dot::after {
    content: "";
    position: absolute;
    top: 22%; right: 22%; bottom: 22%; left: 22%;
    border-radius: 50%;
    background: currentColor;
}
.aq-dot[data-state="ok"] { color: #22c55e; }
.aq-dot[data-state="warn"] { color: #f59e0b; }
.aq-dot[data-state="err"] { color: #f25a5a; }
.aq-dot[data-state="idle"] { color: #81858c; }

/* ============ 检查项行 ============ */
.aq-check-row {
    display: flex;
    align-items: flex-start;
    gap: 0.7rem;
    padding: 0.6rem 0.75rem;
    border-radius: 10px;
    transition: background 0.18s ease;
}
.aq-check-row:hover { background: rgba(255, 255, 255, 0.04); }
.aq-check-item {
    width: 92px;
    flex: none;
    font-size: 0.88rem;
    font-weight: 500;
    color: #f9fafb;
    padding-top: 1px;
}
.aq-check-detail {
    flex: 1;
    font-size: 0.85rem;
    color: #adb2b8;
    line-height: 1.55;
}
.aq-check-dest {
    flex: none;
    font-size: 0.78rem;
    color: #679efe;
    margin-top: 1px;
}

/* ============ Hero CTA 胶囊按钮（叠放在 hero 面板内底部） ============ */
.st-key-aq_hero_ctas {
    position: relative;
    margin-top: -6.2rem;
    padding: 0 3rem 1.8rem;
    z-index: 2;
}
.st-key-aq_hero_ctas [data-testid="stHorizontalBlock"] {
    gap: 0.6rem;
    flex-wrap: wrap;
}
.st-key-aq_hero_ctas [data-testid="stColumn"] {
    width: auto;
    flex: 0 0 auto;
    min-width: 0;
}
.st-key-aq_hero_ctas button {
    border-radius: 999px;
    padding: 0.42rem 1.35rem;
    width: auto;
    min-width: max-content;
    white-space: nowrap;
    background: rgba(16, 24, 42, 0.72);
    border: 1px solid rgba(255, 255, 255, 0.16);
    color: #dbe4f5;
    font-weight: 500;
    backdrop-filter: blur(6px);
    transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease;
}
.st-key-aq_hero_ctas button:hover {
    border-color: rgba(170, 195, 255, 0.55);
    background: rgba(28, 38, 62, 0.85);
    transform: translateY(-1px);
}
.st-key-aq_hero_ctas [data-testid="stColumn"]:first-child button:not(:disabled) {
    background: #f4f7ff;
    color: #0a1222;
    border-color: transparent;
    font-weight: 600;
}
.st-key-aq_hero_ctas [data-testid="stColumn"]:first-child button:not(:disabled):hover {
    background: #ffffff;
}

/* ============ 语言切换（右上角 segmented control 收紧为胶囊组） ============ */
.st-key-aq_lang_toggle {
    display: flex;
    justify-content: flex-end;
}
.st-key-aq_lang_toggle [data-testid="stSegmentedControl"] {
    border-radius: 999px;
}

/* ============ 全屏 hero（DeepSeek Harness 着陆页式，边缘到边缘） ============ */
/* 仅在含 hero 的页面（主页）移除主容器内边距，消除黑边 */
[data-testid="stMainBlockContainer"]:has(.st-key-aq_hero_wrap) {
    padding: 0 0 4rem;
    max-width: none;
}
/* 整页统一深蓝丝绸背景：与 hero 同一渐变、同一角度，fixed 铺满视口并无缝衔接；
   html/body/stApp 也要覆盖，否则页面最顶端会漏出一条深色底 */
html:has(.st-key-aq_hero_wrap),
body:has(.st-key-aq_hero_wrap),
[data-testid="stApp"]:has(.st-key-aq_hero_wrap),
[data-testid="stAppViewContainer"]:has(.st-key-aq_hero_wrap) {
    background: linear-gradient(155deg, #0d2146 0%, #0a1730 46%, #060b18 100%) fixed;
}
/* 主页内隐藏 Streamlit 自带顶栏与装饰条（避免与顶部悬浮导航条重叠，也避免顶栏
   自带的浅色/主题色背景在深蓝渐变最上方露出一条异色带；新版 Streamlit 中
   header/decoration/toolbar 可能渲染在 stAppViewContainer 之外，故从 stApp 起匹配） */
[data-testid="stApp"]:has(.st-key-aq_hero_wrap) [data-testid="stHeader"],
[data-testid="stApp"]:has(.st-key-aq_hero_wrap) [data-testid="stDecoration"],
[data-testid="stApp"]:has(.st-key-aq_hero_wrap) [data-testid="stToolbar"] {
    display: none;
    background: transparent;
}
/* 隐藏顶栏后同时去掉其占位，主内容顶到视口最上沿 */
[data-testid="stAppViewContainer"]:has(.st-key-aq_hero_wrap) [data-testid="stMain"] {
    margin-top: 0;
}
/* 内容区块在零内边距容器里恢复居中留白 */
.st-key-aq_sec_guide,
.st-key-aq_sec_modules,
.st-key-aq_sec_status,
.st-key-aq_sec_runs,
.st-key-aq_sec_detail {
    max-width: 1280px;
    margin-left: auto;
    margin-right: auto;
    padding-left: 3rem;
    padding-right: 3rem;
}
/* 「新手上路」紧跟 hero 之后，标题位于区块左上，不留大块空白 */
.st-key-aq_sec_guide {
    padding-top: 2.5rem;
}
.st-key-aq_hero_wrap {
    position: relative;
    margin: 0;
}
.st-key-aq_hero_wrap .aq-hero {
    margin: 0;
    border: none;
    border-radius: 0;
    min-height: 100vh;                  /* 顶部导航条为固定悬浮，hero 铺满视口 */
    display: flex;
    align-items: center;
    padding: 4.5rem 3rem 8rem;
}
.st-key-aq_hero_wrap .aq-hero-grid {
    width: 100%;
    max-width: 1200px;
    margin: 0 auto;
}

/* ============ 顶部导航条：透明背景，始终悬挂在网页最上端 ============ */
.st-key-aq_stickybar {
    position: fixed;                 /* 固定：任何滚动位置都贴在视口最上沿 */
    top: 0;                          /* 贴紧视口顶，去除顶部留白 gap */
    left: 0;
    right: 0;
    z-index: 1001;
    width: 100%;
    background: transparent;         /* 默认透明，与主页背景一致 */
    transition: background 0.25s ease;
}
.st-key-aq_stickybar [data-testid="stHorizontalBlock"] {
    max-width: 1280px;
    margin: 0 auto;
    align-items: center;
    min-height: 54px;
    gap: 0.7rem;
    padding: 0.7rem 2rem;
}
/* 让每列等高并垂直居中内容，使「已具备回测条件」胶囊、中文/EN、GitHub 处于同一水平线上 */
.st-key-aq_stickybar [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    display: flex !important;
    flex-direction: column;
    justify-content: center;
    align-self: stretch;
}
/* 左侧品牌占满剩余空间，语言切换 + GitHub 靠右并排 */
.st-key-aq_stickybar [data-testid="stColumn"]:first-child {
    flex: 1 1 auto !important;
}
.st-key-aq_stickybar [data-testid="stColumn"]:nth-child(2),
.st-key-aq_stickybar [data-testid="stColumn"]:nth-child(3) {
    flex: 0 0 auto !important;
}
.st-key-aq_stickybar .aq-topbar {
    padding: 0;
    justify-content: flex-start;
}
.st-key-aq_stickybar .aq-brand { gap: 0.6rem; }
.st-key-aq_stickybar .aq-brand-logo {
    width: 28px;
    height: 28px;
    border-radius: 8px;
}
.st-key-aq_stickybar .aq-wordmark {
    font-size: 15px;
    letter-spacing: 0.06em;
}
.st-key-aq_stickybar [data-testid="stSegmentedControl"] {
    border-radius: 999px;
}
/* GitHub 图标 + 文字的胶囊按钮（白色，黑字黑图标，无下划线） */
.aq-github,
.aq-github:visited,
.aq-github:active,
.aq-github:focus {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    height: 34px;
    padding: 0 15px;
    border-radius: 999px;
    background: #f4f7ff;
    color: #000000;
    font-weight: 600;
    font-size: 0.85rem;
    text-decoration: none !important;
    white-space: nowrap;
    transition: background 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
}
.aq-github svg {
    width: 16px;
    height: 16px;
    flex: none;
    fill: #000000;
}
.aq-github:hover,
.aq-github:focus {
    background: #ffffff;
    color: #000000;
    text-decoration: none !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);
}
/* 往下滚动时，导航条从不透明 → 变为非透明（实底 + 轻微毛玻璃） */
@supports (animation-timeline: scroll()) {
    .st-key-aq_stickybar {
        animation: aqNavBlur linear both;
        animation-timeline: scroll(nearest block);
        animation-range: 0 30vh;
    }
    @keyframes aqNavBlur {
        from {
            background: transparent;
            backdrop-filter: none;
            -webkit-backdrop-filter: none;
        }
        to {
            background: rgba(52, 54, 58, 0.97);   /* 灰色、非透明 */
            backdrop-filter: blur(14px) saturate(1.15);
            -webkit-backdrop-filter: blur(14px) saturate(1.15);
        }
    }
}
/* CTA 胶囊叠放在 hero 内底部 */
.st-key-aq_hero_wrap .st-key-aq_hero_ctas {
    margin-top: -7.5rem;
    padding: 0;
}
.st-key-aq_hero_wrap .st-key-aq_hero_ctas [data-testid="stHorizontalBlock"] {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 3rem;
}
/* 白色主 CTA：黑字白底 */
.st-key-aq_hero_ctas [data-testid="stColumn"]:first-child button:not(:disabled),
.st-key-aq_hero_ctas [data-testid="stColumn"]:first-child button:not(:disabled) p {
    background: #f4f7ff;
    color: #0a1222;
    border-color: transparent;
    font-weight: 600;
}
.st-key-aq_hero_ctas [data-testid="stColumn"]:first-child button:not(:disabled):hover,
.st-key-aq_hero_ctas [data-testid="stColumn"]:first-child button:not(:disabled):hover p {
    background: #ffffff;
    color: #000000;
}

/* ============ 下滑渐入（scroll-driven，无 JS；不支持时直接可见） ============ */
/* 注：「新手上路」区块的渐入规则单独在下方维护（大标题 + 逐级延迟）；
   「模块直达」需要继续滚动一段后才缓缓出现，同样单独维护 */
@supports (animation-timeline: view()) {
    .st-key-aq_sec_status,
    .st-key-aq_sec_runs,
    .st-key-aq_sec_detail {
        animation: aqFadeUp linear both;
        animation-timeline: view();
        animation-range: entry 0% entry 45%;
    }
    /* 模块直达：滚动到更近、过程更长的缓慢渐入，与「新手上路」在时间上拉开 */
    .st-key-aq_sec_modules {
        animation: aqFadeUp linear both;
        animation-timeline: view();
        animation-range: entry 5% entry 85%;
    }
}

/* ============ 深蓝底上的卡片统一为蓝色玻璃质感（与 hero 同一色系） ============ */
.st-key-aq_sec_guide [data-testid="stVerticalBlockBorderWrapper"],
.st-key-aq_sec_modules .aq-module-card {
    background: rgba(13, 25, 52, 0.45);
    border-color: rgba(130, 160, 230, 0.18);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
}
.st-key-aq_sec_guide [data-testid="stVerticalBlockBorderWrapper"]:hover,
.st-key-aq_sec_modules .aq-module-card:hover {
    background: rgba(23, 38, 72, 0.60);
    border-color: rgba(150, 180, 255, 0.35);
}
/* 当前建议步骤的卡片轻微提亮，引导视线 */
.st-key-aq_sec_guide [data-testid="stVerticalBlockBorderWrapper"]:has(button[kind="primary"]) {
    border-color: rgba(126, 168, 255, 0.45);
    background: rgba(30, 48, 88, 0.55);
}

/* ============ 新手上路 / 模块直达：大号标题 + 逐级渐入 ============ */
/* 标题放大为区块主标题（区别于普通小节标题），两个区块保持同一字体样式 */
.st-key-aq_sec_guide .aq-section,
.st-key-aq_sec_modules .aq-section {
    margin: 3.4rem 0 1.3rem;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.35rem;
}
.st-key-aq_sec_guide .aq-section-title,
.st-key-aq_sec_modules .aq-section-title {
    font-size: 2.2rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    line-height: 1.2;
    background: linear-gradient(92deg, #f4f7ff 0%, #b9ccff 60%, #7ea8ff 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
}
.st-key-aq_sec_guide .aq-section-hint,
.st-key-aq_sec_modules .aq-section-hint { font-size: 0.95rem; }

/* 双保险动效：默认 time-based 加载渐入（所有浏览器可见）；
   支持 scroll-driven 的浏览器再覆盖为滚动驱动的持续渐显 */
.st-key-aq_sec_guide .aq-section {
    animation: aqFadeUp 0.7s ease-out 0.15s both;
}
[class*="st-key-aq_guide_step_"] {
    animation: aqFadeUp 0.7s ease-out both;
}
.st-key-aq_guide_step_data     { animation-delay: 0.25s; }
.st-key-aq_guide_step_universe { animation-delay: 0.33s; }
.st-key-aq_guide_step_strategy { animation-delay: 0.41s; }
.st-key-aq_guide_step_backtest { animation-delay: 0.49s; }
.st-key-aq_guide_step_review   { animation-delay: 0.57s; }
.st-key-aq_guide_step_paper    { animation-delay: 0.65s; }

@supports (animation-timeline: view()) {
    /* 滚动驱动：标题在较长滚动区间内缓慢浮现，肉眼可感知 */
    .st-key-aq_sec_guide .aq-section {
        animation: aqFadeUp linear both;
        animation-timeline: view();
        animation-range: entry 0% entry 70%;
    }
    [class*="st-key-aq_guide_step_"] {
        animation: aqFadeUp linear both;
        animation-timeline: view();
        animation-delay: 0s;
    }
    .st-key-aq_guide_step_data     { animation-range: entry 12% entry 62%; }
    .st-key-aq_guide_step_universe { animation-range: entry 16% entry 66%; }
    .st-key-aq_guide_step_strategy { animation-range: entry 20% entry 70%; }
    .st-key-aq_guide_step_backtest { animation-range: entry 24% entry 74%; }
    .st-key-aq_guide_step_review   { animation-range: entry 28% entry 78%; }
    .st-key-aq_guide_step_paper    { animation-range: entry 32% entry 82%; }
}

/* 六张步骤卡等高对齐：列拉伸、卡片撑满、按钮吸底。
   列 → stVerticalBlock → stElementContainer → 卡片边框层 的整条链都要撑满，
   否则中间某一环塌陷会导致卡片底边（按钮）参差不齐 */
.st-key-aq_sec_guide [data-testid="stHorizontalBlock"] {
    align-items: stretch;
    gap: 1rem;
}
.st-key-aq_sec_guide [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    display: flex;
    flex-direction: column;
    align-self: stretch;
}
.st-key-aq_sec_guide [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > div {
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
}
.st-key-aq_sec_guide
    [data-testid="stHorizontalBlock"]
    > [data-testid="stColumn"]
    > div
    > [data-testid="stElementContainer"] {
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
}
.st-key-aq_sec_guide [data-testid="stVerticalBlockBorderWrapper"] {
    flex: 1 1 auto;
    /* 等高：列拉伸决定实际高度（各列同高），min-height 兜底。
       无论 Streamlit 版本 DOM 包裹层级如何，内容不满时按钮仍贴底 */
    min-height: 220px;
    display: flex;
    flex-direction: column;
}
.st-key-aq_sec_guide [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"] {
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}
/* 步骤卡 hover 微浮起，与模块卡一致 */
.st-key-aq_sec_guide [data-testid="stVerticalBlockBorderWrapper"] {
    transition: border-color 0.2s ease, background 0.2s ease, transform 0.2s ease;
}
.st-key-aq_sec_guide [data-testid="stVerticalBlockBorderWrapper"]:hover {
    transform: translateY(-2px);
}
/* 说明文字统一预留两行高度：个别步骤说明只有一行（如②股票池），
   不补齐会导致该卡内容更矮、底边与其余五张卡对不齐 */
.st-key-aq_sec_guide [data-testid="stCaptionContainer"] {
    min-height: 2.5rem;
}

/* ============ 最近运行 ============ */
.aq-run-row {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    padding: 0.6rem 0.75rem;
    border-radius: 10px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    transition: background 0.18s ease;
}
.aq-run-row:last-child { border-bottom: none; }
.aq-run-row:hover { background: rgba(255, 255, 255, 0.04); }
.aq-run-label {
    flex: 1;
    min-width: 0;
    font-size: 0.87rem;
    color: #cfd3d6;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.aq-run-meta {
    flex: none;
    font-size: 0.78rem;
    color: #81858c;
    font-variant-numeric: tabular-nums;
}
.aq-run-kind {
    flex: none;
    padding: 1px 8px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.06);
    color: #adb2b8;
    font-size: 0.72rem;
}

/* ============ 模块直达卡片：统一卡片高度 + 「打开」按钮跨列对齐 ============ */
/* 解决英文下标题/描述换行导致同排卡片高度不一、按钮错位的问题 */
.st-key-aq_sec_modules [data-testid="stHorizontalBlock"] {
    align-items: stretch;
    gap: 1rem;
}
/* 每列纵向排列，卡片与按钮天然上下堆叠 */
.st-key-aq_sec_modules [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    display: flex;
    flex-direction: column;
    align-self: stretch;
}
/* 卡片固定高度，保证同一行内所有卡片底部齐平（按钮随之对齐） */
.st-key-aq_sec_modules .aq-module-card {
    height: 240px;
    min-height: 240px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
}
/* 「打开」按钮推到列底部 */
.st-key-aq_sec_modules [data-testid="stColumn"] [data-testid="stElementContainer"]:last-of-type {
    margin-top: auto;
}
/* 标题最多 2 行、描述最多 3 行，超出省略，避免撑破固定高度 */
.st-key-aq_sec_modules .aq-module-title {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.st-key-aq_sec_modules .aq-module-desc {
    flex: 1 1 auto;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
}

/* Final hero overrides: keep the Mac frame fixed and make the editor responsive. */
.st-key-aq_hero_wrap .aq-hero-grid {
    width: min(1160px, 100%);
    max-width: none;
    grid-template-columns: minmax(0, .88fr) minmax(420px, 1fr);
    gap: clamp(3rem, 7vw, 7.5rem);
}
.st-key-aq_hero_wrap .aq-term {
    display: block;
    width: min(100%, 600px);
    height: 420px;
    min-height: 420px;
    animation: aqFadeUp .6s ease-out .3s both !important;
}
.st-key-aq_hero_wrap .aq-term-body { height: 378px; }
.st-key-aq_hero_wrap .aq-term > .aq-term-body > .aq-cursor {
    position: absolute;
    right: 1.7rem;
    bottom: 1.7rem;
}
@media (max-width: 1100px) {
    .st-key-aq_hero_wrap .aq-hero-grid {
        grid-template-columns: minmax(0, 1fr);
        gap: 2.5rem;
        max-width: 720px;
    }
    .st-key-aq_hero_wrap .aq-hero-grid > div:first-child { max-width: 620px; }
    .st-key-aq_hero_wrap .aq-term { width: 100%; max-width: 600px; }
}
@media (max-width: 800px) {
    .st-key-aq_hero_wrap .aq-hero {
        min-height: 100svh;
        height: auto;
        padding: 5.8rem 1.25rem 3.5rem;
    }
    .st-key-aq_hero_wrap .aq-hero-grid { gap: 2rem; }
    .st-key-aq_hero_wrap .aq-hero-title { font-size: clamp(2.6rem, 12vw, 4.2rem); }
    .st-key-aq_hero_wrap .aq-term { height: 360px; min-height: 360px; }
    .st-key-aq_hero_wrap .aq-term-body { height: 318px; }
    .aq-term-scene { padding: 1.45rem 1.35rem 1.8rem; }
    .aq-editor-heading { font-size: 1.45rem; }
}
</style>
"""

_VIBE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Caveat:wght@500;700&family=Fraunces:opsz,wght@9..144,500;9..144,700&family=JetBrains+Mono:wght@400;600&family=Space+Grotesk:wght@400;600;700;800&display=swap');
:root{--vibe-paper:#eef5fd;--vibe-dark:#04060e;--vibe-ember:#ffb454;--vibe-gold:#ffd27a;--vibe-cyan:#7ec8ff}
html,body,[data-testid="stAppViewContainer"]{font-family:"Space Grotesk",-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;background:var(--vibe-dark)}
[data-testid="stMainBlockContainer"]{max-width:1480px;padding-left:clamp(1rem,4vw,4.5rem);padding-right:clamp(1rem,4vw,4.5rem)}
.stApp::before{height:240px;background:radial-gradient(70% 100% at 65% 0%,rgba(36,120,132,.22),transparent 72%)}
.st-key-aq_stickybar{border-bottom:1px solid rgba(255,255,255,.1);padding:.6rem 0 1rem}
.aq-wordmark{font-family:"Space Grotesk",sans-serif;letter-spacing:.02em}.aq-brand-logo{border-radius:50%}
.st-key-aq_hero_wrap .aq-hero{min-height:620px;margin-top:0;border-radius:0 0 28px 28px;padding:5.8rem clamp(1.5rem,5vw,5.5rem) 7rem;background:radial-gradient(circle at 78% 42%,#12323d 0,#07141c 27%,#04060e 65%);border:1px solid rgba(126,200,255,.14)}
.st-key-aq_hero_wrap .aq-hero::before{background:linear-gradient(100deg,transparent 8%,rgba(126,200,255,.22) 38%,rgba(255,210,122,.18) 56%,transparent 92%)}
.st-key-aq_hero_wrap .aq-hero::after{background:linear-gradient(100deg,transparent 10%,rgba(255,180,84,.18) 40%,rgba(126,200,255,.16) 58%,transparent 90%)}
.aq-hero-eyebrow{font:600 11px "JetBrains Mono",monospace;letter-spacing:.14em;color:var(--vibe-cyan)}
.aq-hero-title{font:800 clamp(3.8rem,8vw,8.8rem) "Space Grotesk",sans-serif;letter-spacing:-.08em;line-height:.9;margin:1.5rem 0 1.2rem}.aq-hero-title .aq-accent{font-family:Caveat,cursive;font-weight:500;color:var(--vibe-gold);background:none;-webkit-text-fill-color:initial;letter-spacing:-.03em}
.aq-hero-sub{color:#aab4b7;max-width:590px;font-size:clamp(1rem,1.5vw,1.2rem);line-height:1.7}.aq-hero-badge{border-color:rgba(126,200,255,.35);background:rgba(126,200,255,.1);color:var(--vibe-cyan)}
.aq-term{border-radius:14px;background:rgba(5,7,12,.82);border-color:rgba(255,255,255,.16)}.aq-term-title,.aq-term-body{font-family:"JetBrains Mono",monospace}.aq-term-prompt{color:var(--vibe-cyan)}.aq-term-ok{color:#63d5a0}.aq-term-dim{color:#79858c}
.st-key-aq_hero_ctas button{font-family:"Space Grotesk",sans-serif;background:rgba(5,7,12,.65);border-color:rgba(255,255,255,.2)}.st-key-aq_hero_ctas [data-testid="stColumn"]:first-child button:not(:disabled){background:var(--vibe-paper);color:#101016}.st-key-aq_hero_ctas [data-testid="stColumn"]:first-child button:not(:disabled) p{color:#101016}
.aq-section{margin:4rem 0 1.3rem}.aq-section-title{font:500 clamp(2.4rem,5vw,4.8rem) Fraunces,serif;letter-spacing:-.045em;color:var(--vibe-paper)}.aq-section-hint{color:#879399}.aq-module-card,[data-testid="stVerticalBlockBorderWrapper"]{background:#0c1424;border-color:rgba(126,200,255,.14);border-radius:14px}.aq-module-card:hover,[data-testid="stVerticalBlockBorderWrapper"]:hover{background:#14263f;border-color:rgba(126,200,255,.35)}.aq-module-icon{background:rgba(126,200,255,.1);color:var(--vibe-cyan)}.aq-module-title{color:var(--vibe-paper)}.aq-module-desc{color:#9aabc0}.aq-pill-ok{color:#63d5a0;border-color:rgba(99,213,160,.3);background:rgba(99,213,160,.08)}.aq-pill-warn{color:var(--vibe-gold);border-color:rgba(255,210,122,.3);background:rgba(255,210,122,.08)}
.st-key-aq_sec_guide,.st-key-aq_sec_modules,.st-key-aq_sec_status,.st-key-aq_sec_runs{padding-bottom:2rem}.st-key-aq_sec_detail{color:#9aabc0}.st-key-aq_sec_detail [data-testid="stExpander"]{background:#0c1424}
.aq-product-overview{padding:5.5rem 0 2rem;color:#eef5fd}.aq-overview-heading{max-width:820px}.aq-section-kicker{display:block;font:600 11px "JetBrains Mono",monospace;letter-spacing:.14em;color:#7ec8ff;margin-bottom:1.2rem}.aq-overview-heading h2,.aq-workflow h2{font:500 clamp(2.5rem,5vw,5rem) Fraunces,serif;letter-spacing:-.045em;line-height:1.03;margin:0 0 1.3rem}.aq-overview-heading p{max-width:620px;color:#9aabc0;line-height:1.75;font-size:1.05rem}.aq-product-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin-top:3.2rem}.aq-product-card{min-height:235px;padding:1.35rem 1.4rem;border:1px solid rgba(126,200,255,.16);border-radius:14px;background:linear-gradient(145deg,rgba(13,35,42,.9),rgba(8,15,20,.9));transition:transform .2s ease,border-color .2s ease,background .2s ease}.aq-product-card:hover{transform:translateY(-4px);border-color:rgba(126,200,255,.42);background:linear-gradient(145deg,rgba(18,55,62,.95),rgba(8,15,20,.95))}.aq-product-index{font:11px "JetBrains Mono",monospace;color:#ffb454}.aq-product-card h3{font:500 1.55rem Fraunces,serif;color:#eef5fd;margin:2.6rem 0 .65rem}.aq-product-card p{font-size:.9rem;line-height:1.6;color:#a8b8c8;margin:0}.aq-product-card small{display:block;margin-top:1rem;font:10px "JetBrains Mono",monospace;letter-spacing:.08em;color:#ffd27a}.aq-workflow{margin-top:6.5rem}.aq-flow-grid{display:grid;grid-template-columns:repeat(5,1fr);margin-top:2rem;border-top:1px solid rgba(255,255,255,.16);border-bottom:1px solid rgba(255,255,255,.16)}.aq-flow-node{min-height:130px;padding:1.1rem .8rem;border-right:1px solid rgba(255,255,255,.12);position:relative}.aq-flow-node:last-child{border-right:0}.aq-flow-node b{display:block;font:11px "JetBrains Mono",monospace;color:#7ec8ff;letter-spacing:.08em;margin-bottom:2.2rem}.aq-flow-node span{display:block;color:#b0c0ce;font-size:.82rem;line-height:1.45}.aq-flow-node:not(:last-child)::after{content:"→";position:absolute;right:-9px;top:50%;color:#ffb454;background:#04060e;padding:0 3px;font-size:14px}
 @media(max-width:800px){[data-testid="stMainBlockContainer"]{padding-left:1rem;padding-right:1rem}.st-key-aq_hero_wrap .aq-hero{min-height:680px;padding:5rem 1.4rem 6rem;border-radius:0 0 18px 18px}.aq-hero-title{font-size:5.2rem}.aq-term{display:none}.aq-section-title{font-size:3rem}.aq-product-overview{padding-top:4rem}.aq-overview-heading h2,.aq-workflow h2{font-size:3rem}.aq-product-grid{grid-template-columns:1fr}.aq-product-card{min-height:190px}.aq-product-card h3{margin-top:1.8rem}.aq-flow-grid{grid-template-columns:1fr}.aq-flow-node{min-height:0;padding:1.1rem 0;border-right:0;border-bottom:1px solid rgba(255,255,255,.12)}.aq-flow-node:last-child{border-bottom:0}.aq-flow-node b{margin-bottom:.45rem}.aq-flow-node:not(:last-child)::after{content:"↓";right:.2rem;top:auto;bottom:-10px}.st-key-aq_sec_guide [data-testid="stHorizontalBlock"]{flex-wrap:wrap}.st-key-aq_sec_guide [data-testid="stColumn"]{min-width:46%}}
</style>
"""

# Harness 风格状态图标（Material Symbols Rounded，由 Streamlit 自带字体提供）
_ICONS = {
    "flag": "flag",
    "database": "database",
    "science": "science",
    "candlestick_chart": "candlestick_chart",
    "tune": "tune",
    "history": "history",
    "shield": "shield",
    "account_balance": "account_balance",
    "list_alt": "list_alt",
    "widgets": "widgets",
    "code": "code",
    "psychology": "psychology",
    "search": "search",
    "arrow_forward": "arrow_forward",
}


def inject_global_css() -> None:
    """注入全局主题 CSS；在 ``st.set_page_config`` 之后调用一次即可。"""
    st.markdown(_GLOBAL_CSS + _VIBE_CSS + _WORKBENCH_CSS, unsafe_allow_html=True)


_SIDEBAR_STATE_NOTE = """侧栏的隐藏/显示由 Streamlit 原生控件提供：
收起态由 stSidebarCollapsedControl（左上「»」）展开，
展开态由 stSidebarCollapseButton（侧栏顶「«」）收起。
主题层只负责把这两个控件主题化（见 _GLOBAL_CSS），不再注入自定义开关。"""


def topbar_html(wordmark: str = "FellowQuant", pills: tuple[str, ...] = ()) -> str:
    """生成顶部品牌条 HTML：logo + 字标 + 右侧 pills（每项为完整 HTML）。"""
    logo_path = Path(__file__).parent / "assets" / "fellowquant-logo.png"
    logo_html = ""
    if logo_path.exists():
        import base64

        encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
        logo_html = (
            f'<img class="aq-brand-logo" src="data:image/png;base64,{encoded}" '
            f'alt="FellowQuant"/>'
        )
    pills_html = "".join(pills)
    return f"""
<div class="aq-topbar">
  <div class="aq-brand">
    {logo_html}
    <span class="aq-wordmark">{wordmark}</span>
  </div>
  <div class="aq-topbar-pills">{pills_html}</div>
</div>
"""


def render_topbar(wordmark: str = "FellowQuant", pills: tuple[str, ...] = ()) -> None:
    """渲染顶部品牌条：logo + 字标 + 右侧 pills（每项为完整 HTML）。"""
    st.markdown(topbar_html(wordmark, pills), unsafe_allow_html=True)


def github_link_html(url: str, label: str = "GitHub") -> str:
    """生成带 GitHub 图标的胶囊链接 HTML（深色页面上为白色胶囊按钮）。"""
    icon = (
        '<svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" '
        'aria-hidden="true" role="img"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 '
        '6.53 5.47 7.59.4.08.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94'
        '-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 '
        '1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15'
        '-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 '
        '1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 '
        '3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 '
        '8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>'
    )
    return (
        f'<a class="aq-github" href="{url}" target="_blank" rel="noopener noreferrer" '
        f'aria-label="{label}" title="{label}">'
        f"{icon}<span>{label}</span></a>"
    )


def render_hero(
    title: str,
    subtitle: str,
    accent: str = "",
    badge: str = "",
    eyebrow: str = "",
    topbar: str = "",
    terminal: tuple[str, ...] = (),
    terminal_scenes: tuple[tuple[str, ...], ...] = (),
    terminal_title: str = "fellowquant — zsh",
    scroll_hint: str = "",
    highlights: tuple[tuple[str, str], ...] = (),
) -> None:
    """渲染落地 hero（Harness 风格）：深蓝丝绸光带面板 + 字标 + 悬浮终端卡。

    ``terminal`` 的每一项为一行终端 HTML（可用 aq-term-prompt/ok/dim 类）；
    ``topbar`` 为 :func:`topbar_html` 的输出，悬浮在 hero 面板顶部；
    ``scroll_hint`` 非空时在 hero 底部居中渲染毛玻璃「向下滚动」指示。
    """
    badge_html = f'<span class="aq-hero-badge">{badge}</span>' if badge else ""
    eyebrow_html = f'<div class="aq-hero-eyebrow">{eyebrow}</div>' if eyebrow else ""
    accent_html = f' <span class="aq-accent">{accent}</span>' if accent else ""
    scroll_hint_html = ""
    if scroll_hint:
        scroll_hint_html = (
            '<div class="aq-scroll-hint">'
            f"<span>{scroll_hint}</span>"
            '<svg viewBox="0 0 24 24" aria-hidden="true">'
            '<path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round"/>'
            "</svg></div>"
        )
    term_html = ""
    scenes = terminal_scenes or ((terminal,) if terminal else ())
    if scenes:
        scene_html = "".join(
            f'<div class="aq-term-scene">{"".join(f"<div class=\"aq-term-line\">{line}</div>" for line in scene)}</div>'
            for scene in scenes
        )
        term_html = f"""
  <div class="aq-term">
    <div class="aq-term-bar">
      <span class="aq-term-dot r"></span>
      <span class="aq-term-dot y"></span>
      <span class="aq-term-dot g"></span>
      <span class="aq-term-title">{terminal_title}</span>
    </div>
    <div class="aq-term-body">{scene_html}<span class="aq-cursor"></span></div>
  </div>"""
    highlights_html = ""
    if highlights:
        highlights_html = '<div class="aq-hero-highlights">' + "".join(
            f'<div class="aq-hero-highlight"><span class="aq-highlight-icon">{icon}</span><span>{label}</span></div>'
            for icon, label in highlights
        ) + "</div>"
    st.markdown(
        _LANDING_CSS
        + f"""
<div class="aq-hero">
  {topbar}
  <div class="aq-hero-grid">
    <div>
      {eyebrow_html}
      <div class="aq-hero-title">{title}{accent_html}</div>
      <p class="aq-hero-sub">{subtitle}</p>
      {highlights_html}
      <div style="margin-top:1.1rem;">{badge_html}</div>
    </div>
    {term_html}
  </div>
  {scroll_hint_html}
</div>
""",
        unsafe_allow_html=True,
    )


def render_section(title: str, hint: str = "") -> None:
    """渲染区块标题行。"""
    hint_html = f'<span class="aq-section-hint">{hint}</span>' if hint else ""
    st.markdown(
        f'<div class="aq-section"><span class="aq-section-title">{title}</span>{hint_html}</div>',
        unsafe_allow_html=True,
    )


def render_module_card(
    icon: str,
    title: str,
    desc: str,
    state: str = "idle",
    footer: str = "",
    delay_ms: int = 0,
) -> None:
    """渲染一张模块卡（Harness session-card 风格）。"""
    icon_html = ""
    glyph = _ICONS.get(icon, icon)
    icon_html = f'<span class="aq-module-icon">{glyph}</span>'
    footer_html = (
        f'<div class="aq-module-footer"><span class="aq-dot" data-state="{state}"></span>'
        f"<span>{footer}</span></div>"
        if footer
        else ""
    )
    st.markdown(
        f"""
<div class="aq-module-card" style="animation-delay: {delay_ms}ms;">
  <div class="aq-module-head">{icon_html}</div>
  <div class="aq-module-title">{title}</div>
  <p class="aq-module-desc">{desc}</p>
  {footer_html}
</div>
""",
        unsafe_allow_html=True,
    )


def render_check_row(
    item: str, state: str, detail: str, destination: str = ""
) -> None:
    """渲染一行环境检查（状态圆点 + 项目 + 说明 + 去向）。"""
    dest_html = (
        f'<span class="aq-check-dest">{destination}</span>' if destination else ""
    )
    st.markdown(
        f"""
<div class="aq-check-row">
  <span class="aq-dot" data-state="{state}"></span>
  <span class="aq-check-item">{item}</span>
  <span class="aq-check-detail">{detail}</span>
  {dest_html}
</div>
""",
        unsafe_allow_html=True,
    )


def render_run_row(label: str, state: str, meta: str, kind: str = "") -> None:
    """渲染一行最近运行记录。"""
    kind_html = f'<span class="aq-run-kind">{kind}</span>' if kind else ""
    st.markdown(
        f"""
<div class="aq-run-row">
  <span class="aq-dot" data-state="{state}"></span>
  <span class="aq-run-label">{label}</span>
  {kind_html}
  <span class="aq-run-meta">{meta}</span>
</div>
""",
        unsafe_allow_html=True,
    )
