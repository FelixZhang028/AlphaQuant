"""落地主页：DeepSeek Harness 着陆页风格，由本地配置与数据状态驱动。

布局：顶部品牌条（LOGO+名字 / 中英文切换）→ hero（深蓝丝绸光带面板：介绍 +
悬浮终端卡 + 胶囊功能键 + 向下滚动指示）→ 新手上路（独占一屏）→ 模块直达 →
平台状态 → 最近运行。
"""

from __future__ import annotations

from quant_platform.web.theme import inject_global_css

inject_global_css()


import base64
from html import escape
from pathlib import Path

import streamlit as st

from quant_platform.application.backtest_service import BacktestService
from quant_platform.application.paper_service import PaperTradingService
from quant_platform.application.readiness_service import (
    PlatformReadinessService,
    ReadinessStatus,
)
from quant_platform.application.strategy_studio_service import StrategyStudioService
from quant_platform.backtest.run_store import RunStatus
from quant_platform.web.auth import AuthStore
from quant_platform.web.guide import build_guide_steps
from quant_platform.web.html_compat import javascript_html
from quant_platform.web.run_comparison import RUN_KIND_LABELS
from quant_platform.web.run_labels import format_run_label
from quant_platform.web.theme import (
    github_link_html,
    render_check_row,
    render_hero,
    render_module_card,
    render_run_row,
    render_section,
    topbar_html,
)

_STATE_TO_DOT = {
    ReadinessStatus.READY: "ok",
    ReadinessStatus.WARNING: "warn",
    ReadinessStatus.ACTION: "err",
}

_RUN_TO_DOT = {
    RunStatus.SUCCESS: "ok",
    RunStatus.RUNNING: "warn",
    RunStatus.CREATED: "idle",
    RunStatus.FAILED: "err",
}

_PARTICLE_BACKGROUND_HTML = """
<!doctype html>
<html>
<head>
<style>
  html, body { width:100%; height:100%; margin:0; overflow:hidden; background:transparent; }
  canvas { display:block; width:100%; height:100%; }
</style>
</head>
<body>
<canvas id="aq-particle-canvas" aria-hidden="true"></canvas>
<script>
(() => {
  const canvas = document.getElementById('aq-particle-canvas');
  const ctx = canvas.getContext('2d', { alpha: true });
  if (!ctx) return;

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const mouse = { x: -1000, y: -1000, active: false };
  let width = 1;
  let height = 1;
  let dpr = 1;
  let particles = [];
  let raf = 0;
  let parentDocument = null;

  const host = window.parent;
  try { parentDocument = host.document; } catch (_) { parentDocument = null; }
  const onMove = (event) => {
    mouse.x = event.clientX;
    mouse.y = event.clientY;
    mouse.active = true;
  };
  const onLeave = () => { mouse.active = false; };

  function syncTopbar() {
    try {
      if (!parentDocument) return;
      const splash = parentDocument.querySelector('.aq-launch-splash');
      const scrollHost = parentDocument.querySelector('[data-testid="stMainBlockContainer"]');
      if (!splash) return;
      const scrollTop = scrollHost ? scrollHost.scrollTop : 0;
      const threshold = Math.max(1, splash.offsetTop + splash.offsetHeight - 18);
      parentDocument.documentElement.classList.toggle('aq-welcome-passed', scrollTop >= threshold);
    } catch (_) {
      // Sandboxed st.iframe documents cannot inspect the parent page.
    }
  }

  // The iframe is pointer-transparent; listen on the parent page instead.
  try {
    host.addEventListener('pointermove', onMove, { passive: true });
    host.addEventListener('pointerleave', onLeave, { passive: true });
  } catch (_) {
    window.addEventListener('pointermove', onMove, { passive: true });
  }

  function resize() {
    // st.iframe is sandboxed, so dimensions must come from the iframe itself.
    width = Math.max(1, window.innerWidth);
    height = Math.max(1, window.innerHeight);
    dpr = Math.min(window.devicePixelRatio || 1, 1.6);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const count = Math.min(72, Math.max(36, Math.round((width * height) / 26000)));
    particles = Array.from({ length: count }, () => {
      const x = Math.random() * width;
      const y = Math.random() * height;
      return {
        x, y, baseX: x, baseY: y,
        vx: 0, vy: 0,
        size: Math.random() * 1.5 + .55,
        alpha: Math.random() * .34 + .18,
        tint: Math.random() > .78 ? 'ember' : 'teal',
        phase: Math.random() * Math.PI * 2,
      };
    });
  }

  function draw(time) {
    ctx.clearRect(0, 0, width, height);
    const seconds = time * .001;
    const radius = Math.min(250, Math.max(150, width * .18));

    for (const p of particles) {
      // A tiny idle drift keeps the field alive without creating a constant
      // large-area background animation.
      const driftX = Math.sin(seconds * .22 + p.phase) * .08;
      const driftY = Math.cos(seconds * .18 + p.phase) * .08;
      const homeX = p.baseX + driftX;
      const homeY = p.baseY + driftY;
      const dx = mouse.x - p.x;
      const dy = mouse.y - p.y;
      const distance = Math.hypot(dx, dy);
      const influence = mouse.active && distance < radius
        ? Math.pow(1 - distance / radius, 2)
        : 0;

      // Particles collapse toward the cursor, then softly return to their
      // original field when the pointer leaves the area.
      p.vx += (homeX - p.x) * .0024 + dx * influence * .010;
      p.vy += (homeY - p.y) * .0024 + dy * influence * .010;
      p.vx *= .91;
      p.vy *= .91;
      p.x += p.vx;
      p.y += p.vy;

      const alpha = p.alpha + influence * .30;
      const color = p.tint === 'ember'
        ? `rgba(255, 180, 84, ${alpha})`
        : `rgba(126, 200, 255, ${alpha})`;
      ctx.beginPath();
      ctx.fillStyle = color;
      ctx.arc(p.x, p.y, p.size + influence * 1.2, 0, Math.PI * 2);
      ctx.fill();
    }

    if (!reducedMotion) raf = requestAnimationFrame(draw);
  }

  resize();
  window.addEventListener('resize', resize, { passive: true });
  if (parentDocument) {
    const scrollHost = parentDocument.querySelector('[data-testid="stMainBlockContainer"]');
    (scrollHost || host).addEventListener('scroll', syncTopbar, { passive: true });
    syncTopbar();
    window.setTimeout(syncTopbar, 100);
    window.setTimeout(syncTopbar, 500);
  }
  if (reducedMotion) draw(0);
  else raf = requestAnimationFrame(draw);
})();
</script>
</body>
</html>
"""

_OFFICIAL_HOME_CSS = """
<style>
/* Welcome is an official product page, not the internal workbench shell. */
html, body { margin:0 !important; padding:0 !important; overflow-x:hidden !important; }
[data-testid="stAppViewContainer"], [data-testid="stAppViewContainer"] > section { margin:0 !important; padding:0 !important; }
/* 只在 Welcome 页隐藏导航。不要使用全局选择器，否则切换到工作台后
   Streamlit 会复用这条样式，导致侧栏及其展开按钮永久不可见。 */
html:has(.st-key-aq_hero_wrap) [data-testid="stSidebar"],
html:has(.st-key-aq_hero_wrap) [data-testid="stSidebarCollapsedControl"],
html:has(.st-key-aq_hero_wrap) [data-testid="stExpandSidebarButton"],
html:has(.st-key-aq_hero_wrap) [data-testid="stSidebarCollapseButton"] {
  display:none !important;
}
[data-testid="stMainBlockContainer"] { max-width:none !important; padding:0 !important; }
[data-testid="stMainBlockContainer"] > .stVerticalBlock { gap:0 !important; }
[data-testid="stAppViewContainer"] { background:#04060e !important; }
[data-testid="stHeader"], [data-testid="stToolbar"] { display:none !important; }
[data-testid="stStatusWidget"], #stStatusWidget, div[class*="stStatusWidget"] { display:none !important; }
[data-testid="stMain"] { padding-top:0 !important; margin-top:0 !important; }
[data-testid="stMainBlockContainer"] { margin-top:0 !important; padding-top:0 !important; }
.st-key-aq_stickybar { position:fixed !important; top:0; left:0; right:0; padding:1rem clamp(1.5rem,7vw,7.5rem) .9rem !important; max-width:none; width:auto; margin:0; background:transparent !important; background-color:transparent !important; backdrop-filter:none !important; -webkit-backdrop-filter:none !important; border-bottom:0 !important; box-shadow:none !important; z-index:1001; }
.st-key-aq_stickybar .aq-topbar { mix-blend-mode:difference; }
.st-key-aq_hero_wrap { width:100% !important; max-width:none !important; margin-left:0 !important; }
.st-key-aq_hero_wrap .aq-hero { width:100% !important; max-width:none !important; margin:0 !important; border-radius:0 0 32px 32px !important; }
.st-key-aq_hero_wrap .aq-hero-grid { max-width:1180px; margin:0 auto; }
.st-key-aq_hero_wrap .aq-hero-title { max-width:760px; }
.st-key-aq_hero_wrap .aq-hero-sub { max-width:640px; }
.st-key-aq_hero_wrap .aq-hero::before { opacity:.8; }
.st-key-aq_hero_wrap .aq-hero::after { opacity:.65; }
.st-key-aq_hero_wrap .aq-hero video { display:none; }
.st-key-aq_hero_wrap .aq-term { position:relative; z-index:3; }
.st-key-aq_hero_wrap .aq-hero-ctas { max-width:1180px; margin:0 auto; }
.st-key-aq_hero_wrap .aq-scroll-hint { color:#7ec8ff; }
.aq-product-overview { width:100%; max-width:none; min-height:100vh; margin-left:0; padding:clamp(5rem,9vw,9rem) clamp(1.5rem,8vw,8rem) !important; background:#eef5fd; color:#101016; display:flex; flex-direction:column; justify-content:center; }
.aq-product-overview .aq-section-kicker { color:#2563eb; }
.aq-overview-heading h2, .aq-workflow h2 { color:#101016; max-width:930px; }
.aq-overview-heading p { color:#5e6869; max-width:700px; }
.aq-product-grid { gap:1.25rem; }
.aq-product-card { min-height:260px; background:#eef2ed; border-color:#d4ded7; color:#101016; border-radius:2px; box-shadow:0 8px 24px rgba(16,16,22,.04); }
.aq-product-card:hover { background:#e4ece6; border-color:#8cbdb8; }
.aq-product-card h3 { color:#101016; font-size:1.8rem; }
.aq-product-card p { color:#5e6869; }
.aq-product-card small { color:#e08a3c; }
.aq-workflow-section { width:100%; min-height:100vh; margin-left:0; padding:clamp(5rem,9vw,9rem) clamp(1.5rem,8vw,8rem); background:#eef5fd; display:flex; align-items:center; justify-content:center; }
.aq-workflow { width:min(1180px,100%); margin:0; padding:clamp(2rem,5vw,4rem); border-radius:2px; background:#101c30; color:#eef5fd; }
.aq-workflow .aq-section-kicker { color:#7ec8ff; }
.aq-workflow h2 { color:#eef5fd; font-size:clamp(2.2rem,4vw,4rem); }
.aq-flow-grid { border-color:#ffffff26; }
.aq-flow-node { border-color:#ffffff1c; }
.aq-flow-node b { color:#7ec8ff; }
.aq-flow-node span { color:#b8c3c4; }
.aq-flow-node:not(:last-child)::after { background:#101c30; }
.st-key-aq_sec_guide, .st-key-aq_sec_modules, .st-key-aq_sec_status, .st-key-aq_sec_runs, .st-key-aq_sec_detail { width:100%; max-width:none; margin-left:0; padding-left:clamp(1.5rem,8vw,8rem); padding-right:clamp(1.5rem,8vw,8rem); display:flex; flex-direction:column; justify-content:center; }
.st-key-aq_sec_guide { min-height:100vh; padding-top:6rem; padding-bottom:6rem; }
.st-key-aq_sec_guide .aq-section-title, .st-key-aq_sec_modules .aq-section-title, .st-key-aq_sec_status .aq-section-title, .st-key-aq_sec_runs .aq-section-title { font-size:clamp(2.5rem,5vw,4.7rem); }
.st-key-aq_sec_modules { min-height:100vh; padding-top:6rem; padding-bottom:6rem; background:#070d18; }
.st-key-aq_sec_status { min-height:100vh; margin-top:0; padding-top:6rem; padding-bottom:6rem; background:#eef5fd; color:#101016; max-width:none; }
.st-key-aq_sec_status > div { max-width:1280px; margin-left:auto; margin-right:auto; }
.st-key-aq_sec_status .aq-section-title { color:#101016; }
.st-key-aq_sec_status .aq-section-hint, .st-key-aq_sec_status .aq-check-detail { color:#697273; }
.st-key-aq_sec_status .aq-check-item { color:#101016; }
.st-key-aq_sec_status .aq-check-row:hover { background:#eaf0eb; }
.st-key-aq_sec_runs { min-height:100vh; padding-top:6rem; padding-bottom:6rem; }
.st-key-aq_sec_detail { min-height:55vh; padding-top:5rem; padding-bottom:5rem; }
.st-key-aq_sec_guide [data-testid="stHorizontalBlock"] { align-items:stretch !important; gap:1rem !important; }
.st-key-aq_sec_guide [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { display:flex !important; flex-direction:column !important; align-self:stretch !important; }
.st-key-aq_sec_guide [data-testid="stColumn"] > div { display:flex !important; flex-direction:column !important; flex:1 1 auto !important; }
.st-key-aq_sec_guide [data-testid="stVerticalBlockBorderWrapper"] { height:100% !important; min-height:260px !important; display:flex !important; flex:1 1 auto !important; }
.st-key-aq_sec_guide [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"] { display:flex !important; flex-direction:column !important; justify-content:space-between !important; flex:1 1 auto !important; }
.st-key-aq_sec_guide [data-testid="stCaptionContainer"] { min-height:2.8rem !important; }
.st-key-aq_hero_ctas button, .st-key-aq_sec_guide button, .st-key-aq_sec_modules button, .st-key-aq_sec_status button, .st-key-aq_sec_runs button { position:relative; overflow:hidden; transition:transform .22s cubic-bezier(.22,1,.36,1),box-shadow .22s ease,border-color .22s ease,background .22s ease !important; }
.st-key-aq_hero_ctas button:hover, .st-key-aq_sec_guide button:hover, .st-key-aq_sec_modules button:hover, .st-key-aq_sec_status button:hover, .st-key-aq_sec_runs button:hover { transform:translateY(-3px) !important; box-shadow:0 10px 22px rgba(0,0,0,.22) !important; }
.st-key-aq_hero_ctas button:active, .st-key-aq_sec_guide button:active, .st-key-aq_sec_modules button:active, .st-key-aq_sec_status button:active, .st-key-aq_sec_runs button:active { transform:translateY(-1px) scale(.98) !important; }
.st-key-aq_hero_ctas button::after, .st-key-aq_sec_guide button::after, .st-key-aq_sec_modules button::after, .st-key-aq_sec_status button::after, .st-key-aq_sec_runs button::after { content:""; position:absolute; inset:0; transform:translateX(-110%); background:linear-gradient(105deg,transparent 35%,rgba(255,255,255,.18) 50%,transparent 65%); transition:transform .55s ease; pointer-events:none; }
.st-key-aq_hero_ctas button:hover::after, .st-key-aq_sec_guide button:hover::after, .st-key-aq_sec_modules button:hover::after, .st-key-aq_sec_status button:hover::after, .st-key-aq_sec_runs button:hover::after { transform:translateX(110%); }
@media(max-width:800px){
  .st-key-aq_stickybar { padding-left:1.25rem !important; padding-right:1.25rem !important; }
  .st-key-aq_stickybar [data-testid="stHorizontalBlock"] { display:flex !important; flex-direction:row !important; align-items:center !important; gap:.45rem !important; }
  .st-key-aq_stickybar [data-testid="stColumn"] { width:auto !important; min-width:0 !important; flex:0 0 auto !important; }
  .st-key-aq_stickybar [data-testid="stColumn"]:first-child { flex:1 1 auto !important; }
  .st-key-aq_stickybar [data-testid="stColumn"]:last-child { display:none !important; }
  .st-key-aq_stickybar .aq-topbar { padding:0 !important; }
  .st-key-aq_stickybar .aq-topbar-pills { display:none !important; }
  .st-key-aq_hero_wrap .aq-hero { border-radius:0 0 18px 18px !important; }
  .aq-product-overview { padding-left:1.25rem !important; padding-right:1.25rem !important; min-height:100vh; }
  .aq-workflow-section { padding-left:1.25rem; padding-right:1.25rem; }
  .aq-workflow { padding:1.5rem; }
  .st-key-aq_sec_guide, .st-key-aq_sec_modules, .st-key-aq_sec_runs, .st-key-aq_sec_detail { padding-left:1.25rem; padding-right:1.25rem; min-height:100vh; }
  .st-key-aq_sec_status { padding-left:1.25rem; padding-right:1.25rem; min-height:100vh; }
  .st-key-aq_sec_guide [data-testid="stHorizontalBlock"] { display:grid !important; grid-template-columns:1fr 1fr; }
  .st-key-aq_sec_guide [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { width:auto !important; min-width:0 !important; }
}
</style>
"""

# 首屏关键 CSS：必须在任何欢迎页 HTML 之前注入，避免刷新时出现未样式化闪屏。
# 完整视觉增强仍由 _WELCOME_FINAL_CSS 在页面末尾覆盖。
_WELCOME_CRITICAL_CSS = """
<style>
html, body,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stMainBlockContainer"] {
  margin: 0 !important;
  padding: 0 !important;
  overflow-x: hidden !important;
  background: #04060e !important;
}
[data-testid="stMainBlockContainer"] {
  width: 100% !important;
  max-width: none !important;
}
.st-key-aq_particle_bg {
  position: fixed !important;
  inset: 0 !important;
  width: 100vw !important;
  height: 0 !important;
  min-height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  overflow: visible !important;
  pointer-events: none !important;
  z-index: 1003 !important;
}
.st-key-aq_particle_bg iframe {
  position: fixed !important;
  inset: 0 !important;
  width: 100vw !important;
  height: 100vh !important;
  border: 0 !important;
  pointer-events: none !important;
  z-index: 1003 !important;
}
.st-key-aq_particle_bg canvas {
  position: fixed !important;
  inset: 0 !important;
  display: block !important;
  width: 100vw !important;
  height: 100vh !important;
  pointer-events: none !important;
  z-index: 1003 !important;
}
.st-key-aq_stickybar {
  position: fixed !important;
  isolation: isolate;
  opacity: 0 !important;
  transform: translate3d(0, -14px, 0) !important;
  pointer-events: none !important;
  visibility: hidden !important;
}
html.aq-welcome-passed .st-key-aq_stickybar {
  opacity: 1 !important;
  transform: translate3d(0, 0, 0) !important;
  pointer-events: auto !important;
  visibility: visible !important;
}
.aq-launch-splash {
  position: relative;
  width: 100vw !important;
  min-height: 100svh;
  margin-left: calc(50% - 50vw) !important;
  box-sizing: border-box;
  display: grid;
  place-items: center;
  overflow: hidden;
  color: #eef5fd;
  background:
    radial-gradient(circle at 50% 44%, rgba(35,116,125,.30), transparent 31%),
    radial-gradient(circle at 18% 88%, rgba(255,180,84,.16), transparent 28%),
    linear-gradient(145deg, #081120 0%, #0c1a33 48%, #070b16 100%);
}
.aq-launch-splash::before,
.aq-launch-splash::after {
  animation: none !important;
  will-change: auto !important;
}
.aq-launch-content {
  width: min(92vw, 1120px);
  padding: 4rem 1rem 6rem;
  text-align: center;
  transform: translateY(-1vh);
  position: relative;
  z-index: 3;
}
.aq-launch-title {
  margin: 0;
  color: #eef5fd !important;
  font-family: "Space Grotesk", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: clamp(3.7rem, 8vw, 7.8rem);
  font-weight: 700;
  line-height: .92;
  letter-spacing: -.085em;
}
.aq-launch-typing {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  margin-top: clamp(1.4rem, 3vw, 2.4rem);
  color: #a8b8c8;
  font-family: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
  font-size: clamp(9px, 1vw, 12px);
  line-height: 22px;
  letter-spacing: clamp(2px, .45vw, 6px);
  white-space: nowrap;
}
.aq-launch-phrase {
  display: inline-block;
  width: 50ch;
  max-width: calc(100vw - 3rem);
  overflow: hidden;
  white-space: nowrap;
  animation: aqTypeErase 6.2s linear infinite;
}
@keyframes aqTypeErase {
  0%, 8% { width: 0; }
  47%, 62% { width: 50ch; }
  86%, 100% { width: 0; }
}
.aq-launch-cursor {
  width: 1px;
  height: 17px;
  margin-left: 5px;
  background: #7ec8ff;
  animation: aqLaunchBlink .7s steps(1, end) infinite;
}
@keyframes aqLaunchBlink { 50% { opacity: 0; } }
.aq-launch-scroll {
  position: absolute;
  left: 50%;
  bottom: 2rem;
  display: inline-flex;
  width: 42px;
  height: 42px;
  align-items: center;
  justify-content: center;
  transform: translateX(-50%);
  color: rgba(238,245,253,.78);
  text-decoration: none;
  z-index: 3;
}
.aq-launch-scroll svg { width: 22px; height: 22px; fill: none; stroke: currentColor; stroke-width: 1.7; }
@media (max-width: 800px) {
  .aq-launch-title { font-size: clamp(3.5rem, 16vw, 5.4rem); }
  .aq-launch-typing { letter-spacing: 2px; }
}
</style>
"""

# 这一层样式必须在页面所有组件渲染完成后注入：Streamlit 会为每个
# markdown/container 再套多层 wrapper，页面级的最终覆盖比单独修改某一层更稳定。
_WELCOME_FINAL_CSS = """
<style>
:root {
  --aq-night: #04060e;
  --aq-deep: #081120;
  --aq-teal: #7ec8ff;
  --aq-ember: #ffb454;
  --aq-gold: #ffd27a;
  --aq-paper: #eef5fd;
  --aq-muted: #a8b8c8;
}

/* Topbar is a continuation of the welcome page, not part of the launch screen. */
.st-key-aq_stickybar {
  z-index: 1001;
  opacity: 0 !important;
  visibility: hidden !important;
  pointer-events: none !important;
  transform: translate3d(0, -14px, 0) !important;
  animation: none !important;
  transition: opacity .32s ease, transform .32s cubic-bezier(.22,1,.36,1), visibility 0s linear .32s !important;
}
.st-key-aq_stickybar::before {
  content: "";
  position: absolute;
  z-index: -1;
  top: 0;
  right: -100vw;
  bottom: 0;
  left: -100vw;
  pointer-events: none;
  background: linear-gradient(180deg, rgba(5, 11, 22, .94) 0%, rgba(5, 11, 22, .78) 72%, rgba(5, 11, 22, .18) 100%);
  border-bottom: 1px solid rgba(126, 200, 255, .12);
  box-shadow: 0 12px 32px rgba(0, 0, 0, .16);
  backdrop-filter: blur(12px) saturate(115%);
  -webkit-backdrop-filter: blur(12px) saturate(115%);
}
.st-key-aq_stickybar .aq-topbar { position: relative; z-index: 1; }
html.aq-welcome-passed .st-key-aq_stickybar {
  opacity: 1 !important;
  visibility: visible !important;
  pointer-events: auto !important;
  transform: translate3d(0, 0, 0) !important;
  transition-delay: 0s !important;
}

/* Typora-inspired opening screen: same interaction rhythm, FellowQuant palette. */
.aq-launch-splash {
  position: relative;
  width: 100vw !important;
  min-height: 100svh;
  margin-left: calc(50% - 50vw) !important;
  box-sizing: border-box;
  display: grid;
  place-items: center;
  overflow: hidden;
  isolation: isolate;
  z-index: 1002;
  color: var(--aq-paper);
  background:
    radial-gradient(circle at 50% 44%, rgba(37, 99, 235, .30), transparent 31%),
    radial-gradient(circle at 18% 88%, rgba(255, 180, 84, .16), transparent 28%),
    linear-gradient(145deg, #081120 0%, #0c1a33 48%, #070b16 100%);
}
.aq-launch-splash::before,
.aq-launch-splash::after {
  content: "";
  position: absolute;
  pointer-events: none;
  z-index: -1;
  border-radius: 50%;
  /* Particle canvas replaces continuous background motion. */
  backface-visibility: hidden;
  transform-style: preserve-3d;
  animation: none !important;
  will-change: auto;
}
.aq-launch-splash::before {
  width: min(50vw, 680px);
  height: min(50vw, 680px);
  left: 50%;
  top: 46%;
  transform: translate3d(-50%, -50%, 0) scale(1);
  background: radial-gradient(circle, rgba(126,200,255,.08), transparent 67%);
  opacity: .78;
}
.aq-launch-splash::after {
  width: 42vw;
  height: 20vw;
  left: 3%;
  bottom: -9%;
  background: radial-gradient(ellipse, rgba(255,180,84,.11), transparent 70%);
  transform: translate3d(0, 0, 0) scale(1);
  opacity: .42;
}
@keyframes aqLaunchPulse {
  from { opacity: .68; transform: translate3d(-50%, -50%, 0) scale(.985); }
  to { opacity: .92; transform: translate3d(-50%, -50%, 0) scale(1.015); }
}
@keyframes aqLaunchDrift {
  to { transform: translate3d(7vw, -1.5vh, 0) scale(1.04); opacity: .5; }
}
.aq-launch-content {
  width: min(92vw, 1120px);
  padding: 4rem 1rem 6rem;
  text-align: center;
  transform: translateY(-1vh);
}
.aq-launch-title {
  margin: 0;
  color: var(--aq-paper) !important;
  font-family: "Space Grotesk", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: clamp(3.7rem, 8vw, 7.8rem);
  font-weight: 700;
  line-height: .92;
  letter-spacing: -.085em;
  text-shadow: 0 0 50px rgba(126,200,255,.10);
}
.aq-launch-typing {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  margin-top: clamp(1.4rem, 3vw, 2.4rem);
  color: #a8b8c8;
  font-family: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
  font-size: clamp(9px, 1vw, 12px);
  font-weight: 500;
  line-height: 22px;
  letter-spacing: clamp(2px, .45vw, 6px);
  white-space: nowrap;
}
.aq-launch-phrase {
  display: inline-block;
  /* 28 characters + letter-spacing need roughly 50 monospace ch on desktop. */
  width: 50ch;
  max-width: calc(100vw - 3rem);
  overflow: hidden;
  text-align: left;
  white-space: nowrap;
  /* Linear clipping gives the same readable type/delete rhythm as Typora,
     while keeping the full phrase visible at the end of the type phase. */
  animation: aqTypeErase 6.2s linear infinite;
}
@keyframes aqTypeErase {
  0%, 8% { width: 0; }
  47%, 62% { width: 50ch; }
  86%, 100% { width: 0; }
}
.aq-launch-cursor {
  width: 1px;
  height: 17px;
  margin-left: 5px;
  background: var(--aq-teal);
  animation: aqLaunchBlink .7s steps(1, end) infinite;
}
@keyframes aqLaunchBlink {
  50% { opacity: 0; }
}
.aq-launch-scroll {
  position: absolute;
  left: 50%;
  bottom: clamp(1.3rem, 4vw, 2.6rem);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  transform: translateX(-50%);
  color: rgba(238,245,253,.78);
  border: 0;
  background: transparent;
  text-decoration: none;
  animation: aqLaunchArrow 1.8s ease-in-out infinite;
}
.aq-launch-scroll svg { width: 22px; height: 22px; fill: none; stroke: currentColor; stroke-width: 1.7; }
.aq-launch-scroll:hover { color: var(--aq-teal); }
@keyframes aqLaunchArrow {
  0%, 100% { opacity: .45; transform: translate(-50%, 0); }
  50% { opacity: 1; transform: translate(-50%, 7px); }
}

/* The original Typora hero keeps navigation out of the opening frame. */
@supports (animation-timeline: scroll()) {
  @keyframes aqTopbarReveal {
    from { opacity: 0; transform: translateY(-12px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .st-key-aq_stickybar {
    animation: aqTopbarReveal linear both;
    animation-timeline: scroll(root);
    animation-range: 0 180px;
  }
}
@supports (animation-timeline: scroll(nearest block)) {
  .st-key-aq_stickybar {
    animation: aqTopbarReveal linear both;
    animation-timeline: scroll(nearest block);
    animation-range: 0 180px;
  }
}

/* 页面级画布：每个章节都从 Streamlit 的内容列中“脱出”，铺满视口。 */
html, body,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stMainBlockContainer"] {
  background: var(--aq-night) !important;
  overflow-x: hidden !important;
}
[data-testid="stMainBlockContainer"] {
  width: 100% !important;
  max-width: none !important;
  margin: 0 !important;
  padding: 0 !important;
  scroll-snap-type: y proximity;
  scroll-behavior: smooth;
}
[data-testid="stMainBlockContainer"] > .stVerticalBlock,
[data-testid="stMainBlockContainer"] > .stVerticalBlock > div {
  gap: 0 !important;
  width: 100% !important;
  max-width: none !important;
  padding: 0 !important;
}

/* 全屏章节接近视口顶部时自动贴齐，避免两屏之间残留狭长空隙。 */
.aq-launch-splash,
.st-key-aq_hero_wrap,
.st-key-aq_product_overview_wrap,
.st-key-aq_sec_guide,
.aq-ending-page {
  scroll-snap-align: start;
  scroll-snap-stop: always;
}

/* 顶部栏只负责承载内容，背景完全透明。 */
.st-key-aq_stickybar,
.st-key-aq_stickybar > div,
.st-key-aq_stickybar .aq-topbar {
  background: transparent !important;
  background-color: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
}
.st-key-aq_stickybar .aq-topbar { mix-blend-mode: normal !important; }
.st-key-aq_stickybar .aq-wordmark,
.st-key-aq_stickybar .aq-brand { color: #eef5fd !important; }

/* GitHub 与账户状态组成固定的右上角操作组，首屏无需下拉也能看见。 */
.st-key-aq_welcome_actions {
  position: fixed !important;
  top: 1rem;
  right: clamp(1.25rem, 4vw, 4.5rem);
  z-index: 1100 !important;
  width: auto !important;
}
.st-key-aq_welcome_actions > div,
.st-key-aq_welcome_actions [data-testid="stHorizontalBlock"] {
  width: auto !important;
}
.st-key-aq_welcome_actions [data-testid="stHorizontalBlock"] {
  display: flex !important;
  flex-wrap: nowrap !important;
  align-items: center !important;
  gap: 10px !important;
}
.st-key-aq_welcome_actions [data-testid="stColumn"] {
  width: auto !important;
  min-width: 0 !important;
  flex: 0 0 auto !important;
}
.st-key-aq_welcome_actions [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child {
  flex-basis: 126px !important;
}
.st-key-aq_welcome_github [data-testid="stMarkdownContainer"],
.st-key-aq_welcome_github [data-testid="stMarkdownContainer"] p {
  display: flex !important;
  align-items: center !important;
  height: 48px !important;
  margin: 0 !important;
  line-height: 0 !important;
}
.st-key-aq_welcome_actions .aq-github,
.st-key-aq_welcome_actions .aq-github:visited,
.st-key-aq_welcome_actions .aq-github:active,
.st-key-aq_welcome_actions .aq-github:focus {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 10px !important;
  width: 126px !important;
  height: 48px !important;
  padding: 0 17px !important;
  box-sizing: border-box !important;
  border: 0 !important;
  border-radius: 999px !important;
  background: transparent !important;
  color: #eef5fd !important;
  box-shadow: none !important;
  text-decoration: none !important;
  transition: background .2s ease, color .2s ease !important;
}
.st-key-aq_welcome_actions .aq-github span {
  display: inline-flex !important;
  align-items: center !important;
  height: 22px !important;
  color: #eef5fd !important;
  font-size: 15px !important;
  font-weight: 500 !important;
  line-height: 22px !important;
  letter-spacing: .02em;
}
.st-key-aq_welcome_actions .aq-github svg {
  display: block !important;
  width: 22px !important;
  height: 22px !important;
  flex: 0 0 22px !important;
  fill: #7ec8ff !important;
}
.st-key-aq_welcome_actions .aq-github:hover {
  background: rgba(126,200,255,.08) !important;
  color: #7ec8ff !important;
  transform: none !important;
}
.st-key-aq_welcome_actions .aq-github:focus-visible {
  outline: 2px solid rgba(126,200,255,.72) !important;
  outline-offset: 2px !important;
}
.st-key-aq_welcome_account {
  width: auto !important;
}
.st-key-aq_welcome_account button {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 10px !important;
  min-width: 178px !important;
  height: 48px !important;
  padding: 0 17px !important;
  border: 0 !important;
  border-radius: 999px !important;
  background: transparent !important;
  color: #eef5fd !important;
  box-shadow: none !important;
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
  transition: transform .2s ease, border-color .2s ease, background .2s ease, box-shadow .2s ease !important;
}
.st-key-aq_welcome_account button:hover {
  border: 0 !important;
  background: rgba(126,200,255,.08) !important;
  box-shadow: none !important;
  transform: none;
}
.st-key-aq_welcome_account button:focus-visible {
  outline: 2px solid rgba(126,200,255,.72) !important;
  outline-offset: 2px !important;
}
.st-key-aq_welcome_account [data-testid="stPopover"] > button {
  justify-content: flex-start !important;
}
.st-key-aq_welcome_account button [data-testid="stIconMaterial"],
.st-key-aq_welcome_account button span[class*="material-symbols"] {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  width: 22px !important;
  height: 22px !important;
  flex: 0 0 22px !important;
  color: #7ec8ff !important;
  font-size: 21px !important;
  line-height: 1 !important;
  vertical-align: middle !important;
  /* 与同一按钮内的用户名和下拉箭头保持统一的垂直中心。 */
  transform: none !important;
}
.st-key-aq_welcome_account button [data-testid="stMarkdownContainer"] {
  display: flex !important;
  align-items: center !important;
  min-width: 0 !important;
}
.st-key-aq_welcome_account button p {
  max-width: min(30vw, 190px) !important;
  margin: 0 !important;
  overflow: hidden !important;
  color: #eef5fd !important;
  font-size: 15px !important;
  font-weight: 500 !important;
  line-height: 22px !important;
  letter-spacing: .02em;
  text-overflow: ellipsis !important;
  white-space: nowrap !important;
}
.st-key-aq_welcome_account [data-testid="stPopover"] > button svg {
  width: 18px !important;
  height: 18px !important;
  margin-left: auto !important;
  flex: 0 0 18px !important;
  color: #93a9bd !important;
}
@media (max-width: 640px) {
  .st-key-aq_welcome_actions {
    top: .75rem;
    right: .85rem;
  }
  .st-key-aq_welcome_actions [data-testid="stHorizontalBlock"] {
    gap: 6px !important;
  }
  .st-key-aq_welcome_actions [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child {
    flex-basis: 112px !important;
  }
  .st-key-aq_welcome_actions .aq-github {
    width: 112px !important;
    height: 44px !important;
    padding: 0 14px !important;
  }
  .st-key-aq_welcome_github [data-testid="stMarkdownContainer"],
  .st-key-aq_welcome_github [data-testid="stMarkdownContainer"] p {
    height: 44px !important;
  }
  .st-key-aq_welcome_account button {
    min-width: 154px !important;
    height: 44px !important;
    padding: 0 14px !important;
  }
}

/* 脱离父列后的 full-bleed 章节。100svh 对移动浏览器地址栏更稳定。 */
.st-key-aq_hero_wrap,
.st-key-aq_sec_guide,
.st-key-aq_sec_modules,
.st-key-aq_sec_status,
.st-key-aq_sec_runs,
.st-key-aq_sec_detail,
.aq-product-overview,
.aq-workflow-section {
  width: 100vw !important;
  max-width: none !important;
  margin-left: calc(50% - 50vw) !important;
  box-sizing: border-box !important;
}
.st-key-aq_hero_wrap,
.st-key-aq_sec_guide,
.st-key-aq_sec_modules,
.st-key-aq_sec_status,
.st-key-aq_sec_runs,
.st-key-aq_sec_detail {
  min-height: 100svh !important;
}

/* 01 / THE SYSTEM：与首屏共用深色、青绿、橙色的渐变语汇。 */
.aq-product-overview {
  min-height: 100svh !important;
  padding: clamp(5.5rem, 10vw, 9rem) clamp(1.25rem, 8vw, 8rem) !important;
  justify-content: center;
  color: var(--aq-paper) !important;
  background:
    radial-gradient(circle at 76% 16%, rgba(37, 99, 235, .26), transparent 32%),
    radial-gradient(circle at 13% 84%, rgba(255, 180, 84, .13), transparent 28%),
    linear-gradient(145deg, #081120 0%, #0c1a33 48%, #080d19 100%) !important;
  position: relative;
  overflow: hidden;
}
.st-key-aq_product_overview_wrap {
  width: 100vw !important;
  max-width: none !important;
  min-height: 100svh !important;
  margin-left: calc(50% - 50vw) !important;
  padding: clamp(5rem, 9vw, 8rem) clamp(1.25rem, 8vw, 8rem) !important;
  box-sizing: border-box !important;
  background:
    radial-gradient(circle at 76% 16%, rgba(37, 99, 235, .26), transparent 32%),
    radial-gradient(circle at 13% 84%, rgba(255, 180, 84, .13), transparent 28%),
    linear-gradient(145deg, #081120 0%, #0c1a33 48%, #080d19 100%) !important;
  position: relative !important;
  overflow: hidden !important;
}
.st-key-aq_product_overview_wrap > div { position: relative; z-index: 1; }
.st-key-aq_product_overview_wrap [data-testid="stHtml"] {
  margin-top: clamp(3.25rem, 6vw, 5rem) !important;
}
.st-key-aq_product_overview_wrap iframe {
  position: relative !important;
  z-index: 1 !important;
  display: block !important;
  width: 100% !important;
  height: 430px !important;
  margin-top: clamp(3.25rem, 6vw, 5rem) !important;
  border: 0 !important;
  background: transparent !important;
}
.aq-product-overview::after,
.aq-workflow-section::after,
.st-key-aq_sec_guide::after,
.st-key-aq_sec_modules::after,
.st-key-aq_sec_status::after,
.st-key-aq_sec_runs::after {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: .42;
  background: linear-gradient(115deg, transparent 0 30%, rgba(126,200,255,.04) 48%, transparent 70%);
  transform: translate3d(-25%, 0, 0);
  will-change: auto;
  animation: none;
}
@keyframes aqSheen {
  to { transform: translate3d(25%, 0, 0); }
}
.aq-product-overview > *,
.aq-workflow-section > *,
.st-key-aq_sec_guide > *,
.st-key-aq_sec_modules > *,
.st-key-aq_sec_status > *,
.st-key-aq_sec_runs > *,
.st-key-aq_sec_detail > * {
  position: relative;
  z-index: 1;
}
.aq-product-overview .aq-section-kicker,
.aq-workflow .aq-section-kicker { color: var(--aq-teal) !important; }
.aq-overview-heading h2,
.aq-workflow h2 { color: var(--aq-paper) !important; }
.aq-overview-heading p { color: var(--aq-muted) !important; }
.aq-product-grid { gap: clamp(.8rem, 1.5vw, 1.25rem) !important; }
.aq-product-card {
  min-height: 260px !important;
  padding: 1.45rem !important;
  color: var(--aq-paper) !important;
  background: linear-gradient(145deg, rgba(17, 40, 76, .78), rgba(8, 16, 30, .86)) !important;
  border: 1px solid rgba(126, 200, 255, .2) !important;
  border-radius: 16px !important;
  box-shadow: 0 20px 60px rgba(0,0,0,.18) !important;
  transition: transform .28s cubic-bezier(.22,1,.36,1), border-color .28s ease, background .28s ease !important;
}
.aq-product-card:hover {
  transform: translateY(-6px) !important;
  border-color: rgba(126, 200, 255, .46) !important;
  background: linear-gradient(145deg, rgba(27, 56, 104, .9), rgba(9, 18, 32, .92)) !important;
}
.aq-product-card h3 { color: var(--aq-paper) !important; }
.aq-product-card p { color: var(--aq-muted) !important; }
.aq-product-card small { color: var(--aq-gold) !important; }

/* 02 / RESEARCH LOOP：保留面板层次，但与 THE SYSTEM 使用同一套渐变。 */
.aq-workflow-section {
  min-height: 100svh !important;
  padding: clamp(5.5rem, 10vw, 9rem) clamp(1.25rem, 8vw, 8rem) !important;
  background:
    radial-gradient(circle at 18% 18%, rgba(126, 200, 255, .17), transparent 30%),
    radial-gradient(circle at 88% 82%, rgba(255, 180, 84, .14), transparent 30%),
    linear-gradient(145deg, #081120 0%, #101d36 48%, #080d19 100%) !important;
  position: relative;
  overflow: hidden;
}
.aq-workflow {
  width: min(1180px, 100%) !important;
  margin: 0 !important;
  padding: clamp(2rem, 5vw, 4rem) !important;
  color: var(--aq-paper) !important;
  background: linear-gradient(145deg, rgba(19, 54, 61, .72), rgba(8, 16, 30, .76)) !important;
  border: 1px solid rgba(126, 200, 255, .2) !important;
  border-radius: 24px !important;
  box-shadow: 0 24px 80px rgba(0,0,0,.22) !important;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
}
.aq-flow-grid { border-color: rgba(255,255,255,.18) !important; }
.aq-flow-node { border-color: rgba(255,255,255,.12) !important; }
.aq-flow-node b { color: var(--aq-teal) !important; }
.aq-flow-node span { color: #b6c8da !important; }
.aq-flow-node:not(:last-child)::after { background: #101d36 !important; }

/* 后续章节也用同一套深色渐变，避免状态页、记录页突然变白。 */
.st-key-aq_sec_guide {
  position: relative;
  background:
    radial-gradient(circle at 82% 18%, rgba(255, 180, 84, .13), transparent 30%),
    linear-gradient(150deg, #081120 0%, #0d1a30 52%, #070b16 100%) !important;
}
.st-key-aq_sec_modules {
  position: relative;
  background:
    radial-gradient(circle at 12% 70%, rgba(126, 200, 255, .15), transparent 30%),
    linear-gradient(150deg, #081120 0%, #101d36 50%, #070b15 100%) !important;
}
.st-key-aq_sec_status {
  position: relative;
  background:
    radial-gradient(circle at 20% 18%, rgba(126, 200, 255, .16), transparent 32%),
    radial-gradient(circle at 88% 86%, rgba(255, 180, 84, .13), transparent 28%),
    linear-gradient(145deg, #081120 0%, #101d36 52%, #070b15 100%) !important;
  color: var(--aq-paper) !important;
}
.st-key-aq_sec_runs,
.st-key-aq_sec_detail {
  position: relative;
  background:
    radial-gradient(circle at 78% 22%, rgba(37, 99, 235, .2), transparent 30%),
    linear-gradient(145deg, #081120 0%, #0c1729 54%, #070b16 100%) !important;
  color: var(--aq-paper) !important;
}
.st-key-aq_sec_status .aq-section-title,
.st-key-aq_sec_runs .aq-section-title,
.st-key-aq_sec_detail .aq-section-title { color: var(--aq-paper) !important; }
.st-key-aq_sec_status .aq-section-hint,
.st-key-aq_sec_status .aq-check-detail,
.st-key-aq_sec_runs .aq-section-hint { color: #9cb2c4 !important; }
.st-key-aq_sec_status .aq-check-item { color: var(--aq-paper) !important; }
.st-key-aq_sec_status .aq-check-row {
  border: 1px solid rgba(126,200,255,.1);
  background: rgba(10, 22, 42, .42);
  transition: transform .22s ease, background .22s ease, border-color .22s ease;
}
.st-key-aq_sec_status .aq-check-row:hover {
  transform: translateX(4px);
  background: rgba(20, 46, 86, .62) !important;
  border-color: rgba(126,200,255,.3);
}
.st-key-aq_sec_status [data-testid="stExpander"],
.st-key-aq_sec_detail [data-testid="stExpander"] {
  background: rgba(12, 26, 48, .7) !important;
  border-color: rgba(126,200,255,.18) !important;
  color: var(--aq-paper) !important;
}
.st-key-aq_sec_status [style*="color:#81858c"],
.st-key-aq_sec_runs [style*="color:#81858c"] { color: #9cb2c4 !important; }

/* 引导卡：所有 DOM 层都获得同一高度，股票池不会再因少一行文字而塌陷。 */
.st-key-aq_sec_guide [class*="st-key-aq_guide_step_"] {
  height: 214px !important;
  min-height: 214px !important;
  box-sizing: border-box !important;
  display: flex !important;
  flex-direction: column !important;
}
.st-key-aq_sec_guide [class*="st-key-aq_guide_step_"] > div,
.st-key-aq_sec_guide [class*="st-key-aq_guide_step_"] [data-testid="stVerticalBlockBorderWrapper"],
.st-key-aq_sec_guide [class*="st-key-aq_guide_step_"] [data-testid="stVerticalBlock"] {
  flex: 1 1 auto !important;
  display: flex !important;
  flex-direction: column !important;
  box-sizing: border-box !important;
}
.st-key-aq_sec_guide [class*="st-key-aq_guide_step_"] [data-testid="stButton"] {
  margin-top: auto !important;
}
.st-key-aq_sec_guide [data-testid="stHorizontalBlock"] {
  align-items: stretch !important;
}
.st-key-aq_sec_guide [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
  display: flex !important;
  flex-direction: column !important;
  align-self: stretch !important;
}
.st-key-aq_sec_guide [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > div {
  display: flex !important;
  flex: 1 1 auto !important;
  flex-direction: column !important;
}

/* 滚动进入渐显：现代浏览器按 viewport 驱动，旧浏览器仍保持可见。 */
@keyframes aqReveal {
  from { opacity: 0; transform: translateY(34px); filter: blur(5px); }
  to { opacity: 1; transform: translateY(0); filter: blur(0); }
}
@keyframes aqChildReveal {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
.st-key-aq_sec_guide [class*="st-key-aq_guide_step_"],
.st-key-aq_sec_modules .aq-module-card {
  animation: aqReveal .8s cubic-bezier(.22,1,.36,1) both;
}
.st-key-aq_sec_guide [class*="st-key-aq_guide_step_"] [data-testid="stMarkdownContainer"],
.st-key-aq_sec_guide [class*="st-key-aq_guide_step_"] [data-testid="stCaptionContainer"],
.st-key-aq_sec_guide [class*="st-key-aq_guide_step_"] [data-testid="stButton"],
.st-key-aq_sec_modules .aq-module-title,
.st-key-aq_sec_modules .aq-module-desc,
.st-key-aq_sec_modules .aq-module-footer,
.st-key-aq_sec_modules [data-testid="stButton"] {
  animation: aqChildReveal .6s cubic-bezier(.22,1,.36,1) both;
}
.st-key-aq_sec_guide [class*="st-key-aq_guide_step_"]:nth-child(1), .st-key-aq_sec_modules .aq-module-card:nth-of-type(1) { animation-delay: .04s; }
.st-key-aq_sec_guide [class*="st-key-aq_guide_step_"]:nth-child(2), .st-key-aq_sec_modules .aq-module-card:nth-of-type(2) { animation-delay: .12s; }
.st-key-aq_sec_guide [class*="st-key-aq_guide_step_"]:nth-child(3), .st-key-aq_sec_modules .aq-module-card:nth-of-type(3) { animation-delay: .20s; }
.st-key-aq_sec_guide [class*="st-key-aq_guide_step_"]:nth-child(4), .st-key-aq_sec_modules .aq-module-card:nth-of-type(4) { animation-delay: .28s; }
.st-key-aq_sec_guide [class*="st-key-aq_guide_step_"]:nth-child(5), .st-key-aq_sec_modules .aq-module-card:nth-of-type(5) { animation-delay: .36s; }
.st-key-aq_sec_guide [class*="st-key-aq_guide_step_"]:nth-child(6), .st-key-aq_sec_modules .aq-module-card:nth-of-type(6) { animation-delay: .44s; }
.st-key-aq_sec_modules .aq-module-card {
  height: 240px !important;
  min-height: 240px !important;
  box-sizing: border-box !important;
}
.st-key-aq_sec_modules [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
  display: flex !important;
  flex-direction: column !important;
  align-self: stretch !important;
}
.st-key-aq_sec_modules [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > div {
  display: flex !important;
  flex-direction: column !important;
  flex: 1 1 auto !important;
}
.st-key-aq_sec_modules [data-testid="stButton"] { margin-top: 0 !important; }

@supports (animation-timeline: view()) {
  .st-key-aq_sec_guide [class*="st-key-aq_guide_step_"],
  .st-key-aq_sec_modules .aq-module-card {
    animation-timeline: view() !important;
    animation-range: entry 8% entry 52% !important;
  }
  .st-key-aq_sec_guide [class*="st-key-aq_guide_step_"]:nth-child(2),
  .st-key-aq_sec_modules .aq-module-card:nth-of-type(2) { animation-range: entry 14% entry 58% !important; }
  .st-key-aq_sec_guide [class*="st-key-aq_guide_step_"]:nth-child(3),
  .st-key-aq_sec_modules .aq-module-card:nth-of-type(3) { animation-range: entry 20% entry 64% !important; }
  .st-key-aq_sec_guide [class*="st-key-aq_guide_step_"]:nth-child(4),
  .st-key-aq_sec_modules .aq-module-card:nth-of-type(4) { animation-range: entry 26% entry 70% !important; }
  .st-key-aq_sec_guide [class*="st-key-aq_guide_step_"]:nth-child(5),
  .st-key-aq_sec_modules .aq-module-card:nth-of-type(5) { animation-range: entry 32% entry 76% !important; }
  .st-key-aq_sec_guide [class*="st-key-aq_guide_step_"]:nth-child(6),
  .st-key-aq_sec_modules .aq-module-card:nth-of-type(6) { animation-range: entry 38% entry 82% !important; }
}

/* Typora-style feature gallery: a quiet heading followed by small Mac previews. */
.aq-product-overview {
  min-height: 100svh !important;
  justify-content: flex-start !important;
  padding-top: clamp(5rem, 9vw, 8rem) !important;
  padding-bottom: clamp(5rem, 9vw, 8rem) !important;
}
.aq-overview-heading {
  width: min(1180px, 100%);
  margin: 0 auto;
  text-align: center;
}
.aq-overview-heading h2 {
  font-size: clamp(2.6rem, 5vw, 5.4rem) !important;
  letter-spacing: -.065em !important;
  line-height: .98 !important;
  margin: 0 auto 1.6rem !important;
}
.aq-overview-heading p {
  max-width: 680px !important;
  margin: 0 auto !important;
  font-size: clamp(.92rem, 1.15vw, 1.05rem) !important;
}
.aq-feature-grid {
  width: min(1180px, 100%);
  margin: clamp(3.5rem, 7vw, 6rem) auto 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: clamp(2.8rem, 5vw, 5.5rem) clamp(1.2rem, 2.4vw, 2rem);
}
.aq-feature-card { min-width: 0; }
.aq-feature-window {
  height: 210px;
  overflow: hidden;
  border: 1px solid rgba(126,200,255,.24);
  border-radius: 10px;
  background: linear-gradient(145deg, rgba(27,43,49,.96), rgba(5,12,17,.98));
  box-shadow: 0 18px 45px rgba(0,0,0,.28), 0 0 0 1px rgba(255,255,255,.03) inset;
  transition: transform .35s cubic-bezier(.22,1,.36,1), border-color .35s ease, box-shadow .35s ease;
}
.aq-feature-card:hover .aq-feature-window {
  transform: translateY(-7px);
  border-color: rgba(126,200,255,.62);
  box-shadow: 0 25px 60px rgba(0,0,0,.38), 0 0 32px rgba(126,200,255,.08);
}
.aq-feature-bar {
  height: 30px;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 0 10px;
  box-sizing: border-box;
  background: linear-gradient(180deg, #22345a, #16223c);
  border-bottom: 1px solid rgba(126,200,255,.14);
}
.aq-feature-bar > span { width: 8px; height: 8px; border-radius: 50%; }
.aq-feature-bar .r { background: #ff5f57; }
.aq-feature-bar .y { background: #febc2e; }
.aq-feature-bar .g { background: #28c840; }
.aq-feature-bar small { margin-left: 8px; color: #8da4ba; font: 10px "JetBrains Mono", monospace; }
.aq-feature-body { height: 180px; padding: 20px 18px; box-sizing: border-box; color: #b8c9d8; font: 11px "JetBrains Mono", monospace; }
.aq-mini-row { display: flex; gap: 8px; align-items: center; margin-bottom: 18px; }
.aq-mini-row i { width: 7px; height: 7px; border-radius: 50%; background: #7ec8ff; }.aq-mini-row b { color: #eef5fb; }.aq-mini-row span { color: #7f97ae; font-size: 9px; }
.aq-mini-chart { display: flex; align-items: end; gap: 8px; height: 70px; padding: 0 5px; border-bottom: 1px solid rgba(126,200,255,.18); }.aq-mini-chart em { display:block; width: 13%; border-radius: 3px 3px 0 0; background: linear-gradient(#7ec8ff, #2563eb); }.aq-mini-chart em:nth-child(1){height:35%}.aq-mini-chart em:nth-child(2){height:52%}.aq-mini-chart em:nth-child(3){height:44%}.aq-mini-chart em:nth-child(4){height:70%}.aq-mini-chart em:nth-child(5){height:58%}.aq-mini-chart em:nth-child(6){height:86%}
.aq-mini-status { margin-top: 14px; color: #63d5a0; font-size: 10px; }
.aq-mini-code { line-height: 2; color: #aec2d4; }.aq-mini-code span { color: #ffcf9e; }.aq-mini-code strong { color: #7ec8ff; }.aq-mini-pill { margin-top: 13px; color: #ffd27a; font-size: 9px; letter-spacing: .12em; }
.aq-mini-metrics { display:grid; grid-template-columns: auto 1fr; column-gap: 12px; align-items: baseline; }.aq-mini-metrics b { color:#eef5fd; font-size:20px; }.aq-mini-metrics span { color:#7f97ae; font-size:9px; }
.aq-mini-chart.line { margin-top: 15px; }.aq-mini-chart.line em { background: linear-gradient(135deg, transparent 20%, #7ec8ff 21% 28%, transparent 29% 42%, #7ec8ff 43% 51%, transparent 52% 64%, #7ec8ff 65% 72%, transparent 73%); height: 80%; }
.aq-mini-agent { display:flex; align-items:center; gap:10px; height:37px; border-bottom:1px solid rgba(255,255,255,.07); }.aq-mini-agent i { color:#7ec8ff; font-style:normal; font-size:16px; }.aq-mini-agent span { flex:1; color:#e4eef6; }.aq-mini-agent b { color:#63d5a0; font-size:9px; font-weight:400; }
.aq-mini-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:9px; color:#8da4ba; }.aq-mini-grid b { color:#7ec8ff; font-size:9px; }.aq-mini-grid span { color:#eef5fb; }
.aq-mini-order { display:grid; grid-template-columns:42px 1fr 1fr; align-items:center; height:38px; border-bottom:1px solid rgba(255,255,255,.07); }.aq-mini-order span { color:#63d5a0; font-size:9px; }.aq-mini-order b { color:#eef5fb; }.aq-mini-order em { color:#8da4ba; font-style:normal; font-size:9px; }.aq-mini-order strong { grid-column: 3; color:#63d5a0; font-size:9px; font-weight:400; text-align:right; }
.aq-feature-meta { padding: 1.25rem .25rem 0; }.aq-feature-meta > span { color: var(--aq-ember); font: 10px "JetBrains Mono", monospace; letter-spacing: .12em; }.aq-feature-meta h3 { margin: .55rem 0 .45rem; color: var(--aq-paper); font: 500 clamp(1.35rem, 2vw, 1.8rem) Fraunces, serif; letter-spacing: -.035em; }.aq-feature-meta p { margin:0; color: var(--aq-muted); font-size: .86rem; line-height:1.65; }

/* Single-window feature carousel, matching Typora's click-to-preview rhythm. */
.aq-feature-tabs { width:min(980px,100%); margin:clamp(3rem,6vw,5rem) auto 1.8rem; display:flex; justify-content:center; gap:clamp(1rem,3vw,3rem); border-bottom:1px solid rgba(126,200,255,.16); }
.aq-feature-tab { position:relative; padding:0 0 .8rem; border:0; background:transparent; color:#7288a0; font:500 clamp(.82rem,1.2vw,1rem) "Space Grotesk",sans-serif; cursor:pointer; transition:color .25s ease,transform .25s ease; }
.aq-feature-tab span { display:block; margin-bottom:.35rem; color:#ffb454; font:9px "JetBrains Mono",monospace; letter-spacing:.12em; }
.aq-feature-tab::after { content:""; position:absolute; left:0; right:0; bottom:-1px; height:2px; background:#7ec8ff; transform:scaleX(0); transition:transform .3s ease; }
.aq-feature-tab:hover,.aq-feature-tab.is-active { color:#eef5fd; transform:translateY(-2px); }.aq-feature-tab.is-active::after { transform:scaleX(1); }
.aq-feature-stage { position:relative; width:min(860px,100%); height:300px; margin:0 auto; overflow:hidden; }
.aq-feature-slide { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; margin:0; opacity:0; pointer-events:none; transform:translateX(112%); transition:transform .55s cubic-bezier(.22,1,.36,1),opacity .42s ease; }
.aq-feature-slide[data-state="active"] { opacity:1; transform:translateX(0); pointer-events:auto; }.aq-feature-slide[data-state="past"] { opacity:0; transform:translateX(-112%); }.aq-feature-slide[data-state="next"] { opacity:0; transform:translateX(112%); }
.aq-feature-slide .aq-feature-window { width:min(560px,100%); height:220px; flex:none; }.aq-feature-slide > p { max-width:560px; margin:1rem 0 0; color:#a8b8c8; text-align:center; font-size:.9rem; line-height:1.6; }

@media (max-width: 900px) {
  .aq-feature-tabs { gap:1.15rem; overflow-x:auto; justify-content:flex-start; padding:0 .5rem; }
  .aq-feature-tab { flex:0 0 auto; }
}
@media (max-width: 560px) {
  .aq-overview-heading h2 { font-size: clamp(2.5rem, 12vw, 4rem) !important; }
  .aq-feature-stage { height:285px; }.aq-feature-slide .aq-feature-window { height:210px; }.aq-feature-slide > p { padding:0 .8rem; }
}

/* 02 / RESEARCH LOOP：Typora 式的居中标题 + 两行三列步骤卡。 */
.st-key-aq_sec_guide {
  justify-content: flex-start !important;
  padding-top: clamp(5.5rem, 9vw, 8rem) !important;
  padding-bottom: clamp(5.5rem, 9vw, 8rem) !important;
}
.aq-research-loop-heading {
  width: min(1080px, 100%);
  margin: 0 auto;
  text-align: center;
}
.aq-research-loop-heading .aq-section-kicker {
  display: block;
  margin-bottom: 1.15rem;
  color: var(--aq-teal) !important;
  font: 10px "JetBrains Mono", monospace;
  letter-spacing: .22em;
}
.aq-research-loop-heading h2 {
  margin: 0 auto 1.25rem;
  color: var(--aq-paper) !important;
  font: 500 clamp(2.8rem, 5vw, 5.4rem) Fraunces, serif;
  letter-spacing: -.065em;
  line-height: .98;
}
.aq-research-loop-heading p {
  max-width: 680px;
  margin: 0 auto;
  color: var(--aq-muted) !important;
  font-size: clamp(.92rem, 1.15vw, 1.05rem);
  line-height: 1.7;
}
.st-key-aq_sec_guide [data-testid="stHorizontalBlock"] {
  width: min(1260px, 100%) !important;
  margin: clamp(3.25rem, 6vw, 5rem) auto 0 !important;
  display: grid !important;
  grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
  gap: clamp(1rem, 2vw, 1.5rem) !important;
  align-items: stretch !important;
}
.st-key-aq_sec_guide [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
  width: 100% !important;
  min-width: 0 !important;
  display: flex !important;
  align-items: stretch !important;
}
.st-key-aq_sec_guide [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > div {
  width: 100% !important;
  min-width: 0 !important;
  display: flex !important;
  flex: 1 1 auto !important;
}
.st-key-aq_sec_guide [data-testid="stVerticalBlockBorderWrapper"] {
  width: 100% !important;
  min-width: 0 !important;
  min-height: 360px !important;
  height: 360px !important;
  padding: 1.25rem 1.3rem !important;
  border: 1px solid rgba(126,200,255,.18) !important;
  border-radius: 12px !important;
  background: linear-gradient(145deg, rgba(18,51,59,.68), rgba(7,15,21,.8)) !important;
  box-shadow: 0 18px 48px rgba(0,0,0,.14) !important;
  transition: transform .3s cubic-bezier(.22,1,.36,1), border-color .3s ease, background .3s ease, box-shadow .3s ease !important;
}
.st-key-aq_sec_guide [data-testid="stVerticalBlockBorderWrapper"]:hover {
  transform: translateY(-6px) !important;
  border-color: rgba(126,200,255,.48) !important;
  background: linear-gradient(145deg, rgba(26,70,77,.82), rgba(8,16,22,.9)) !important;
  box-shadow: 0 24px 56px rgba(0,0,0,.25), 0 0 26px rgba(126,200,255,.06) !important;
}
.st-key-aq_sec_guide [data-testid="stVerticalBlockBorderWrapper"]:has(button[kind="primary"]) {
  border-color: rgba(255,180,84,.48) !important;
  background: linear-gradient(145deg, rgba(64,47,42,.62), rgba(15,19,23,.88)) !important;
}
.aq-guide-preview {
  width: 100%;
  height: 150px;
  flex: 0 0 150px;
  overflow: hidden;
  padding: 1rem;
  box-sizing: border-box;
  border: 1px solid rgba(126,200,255,.15);
  border-radius: 8px;
  background: linear-gradient(145deg, rgba(25,47,53,.92), rgba(6,15,20,.96));
  color: #b8c9d8;
  font: 10px "JetBrains Mono", monospace;
  transition: border-color .3s ease, box-shadow .3s ease, transform .3s ease;
}
.st-key-aq_sec_guide [data-testid="stVerticalBlockBorderWrapper"]:hover .aq-guide-preview {
  border-color: rgba(126,200,255,.48);
  box-shadow: 0 0 24px rgba(126,200,255,.1), inset 0 0 18px rgba(126,200,255,.04);
  transform: scale(1.015);
}
.aq-preview-top { display:flex; align-items:center; justify-content:space-between; color:#8da4ba; font-size:9px; letter-spacing:.1em; }
.aq-preview-top b { color:#63d5a0; font-weight:400; }
.aq-preview-chart { height:78px; display:flex; align-items:end; gap:7px; margin-top:15px; padding:0 4px; border-bottom:1px solid rgba(126,200,255,.18); }
.aq-preview-chart i { display:block; width:12%; border-radius:3px 3px 0 0; background:linear-gradient(#7ec8ff,#2563eb); }
.aq-preview-chart i:nth-child(1){height:38%}.aq-preview-chart i:nth-child(2){height:54%}.aq-preview-chart i:nth-child(3){height:46%}.aq-preview-chart i:nth-child(4){height:72%}.aq-preview-chart i:nth-child(5){height:60%}.aq-preview-chart i:nth-child(6){height:88%}.aq-preview-chart i:nth-child(7){height:76%}
.aq-preview-foot { margin-top:10px; color:#7ec8ff; font-size:9px; letter-spacing:.08em; }
.aq-preview-list { display:grid; gap:9px; margin-top:18px; color:#dbe8f4; }
.aq-preview-list span { padding-bottom:7px; border-bottom:1px solid rgba(255,255,255,.08); }
.aq-access-lines { display:grid; gap:10px; margin-top:22px; }.aq-access-lines i { display:block; width:72%; height:7px; border-radius:999px; background:linear-gradient(90deg,#7ec8ff,#1d4ed8); opacity:.9; }.aq-access-lines i.wide { width:92%; height:11px; }.aq-access-lines i.short { width:48%; opacity:.55; }
.aq-preview-inputs { display:flex; flex-wrap:wrap; gap:7px; margin-top:18px; }.aq-preview-inputs span { padding:5px 8px; border:1px solid rgba(126,200,255,.22); border-radius:999px; color:#aec2d4; }.aq-preview-inputs span.active { border-color:#7ec8ff; color:#7ec8ff; background:rgba(126,200,255,.1); }
.aq-preview-code { display:grid; gap:8px; margin-top:17px; color:#b8c9d8; line-height:1.35; }
.aq-preview-code em { color:#ffcf9e; font-style:normal; }.aq-preview-code strong { color:#7ec8ff; font-weight:400; }
.aq-preview-metrics { display:grid; grid-template-columns:auto 1fr; gap:8px 10px; align-items:baseline; margin-top:15px; }.aq-preview-metrics b { color:#eef5fd; font-size:20px; }.aq-preview-metrics span { color:#7f97ae; font-size:9px; }
.aq-preview-focus { display:grid; gap:8px; margin-top:18px; }.aq-preview-focus span { color:#8da4ba; font-size:9px; }.aq-preview-focus b { color:#eef5fd; font-size:25px; }.aq-preview-focus .muted { opacity:.35; }
.aq-preview-line { height:34px; margin-top:13px; border-bottom:2px solid #7ec8ff; clip-path:polygon(0 80%, 12% 68%, 25% 74%, 38% 38%, 51% 54%, 65% 20%, 77% 40%, 88% 10%, 100% 24%, 100% 100%, 0 100%); background:linear-gradient(135deg, transparent 12%, rgba(126,200,255,.18) 13% 18%, transparent 19% 30%, rgba(126,200,255,.22) 31% 36%, transparent 37%); }
.aq-preview-report { display:grid; gap:12px; margin-top:16px; }.aq-preview-report span { color:#dbe8f4; }.aq-preview-report i { display:inline-block; width:7px; height:7px; margin-right:8px; border-radius:50%; background:#63d5a0; }
.aq-preview-safe { display:grid; gap:9px; margin-top:18px; }.aq-preview-safe span { color:#8da4ba; font-size:9px; }.aq-preview-safe b { color:#eef5fd; font-size:16px; }.aq-preview-safe em { color:#63d5a0; font-style:normal; font-size:9px; }
.aq-preview-orders { display:grid; gap:13px; margin-top:18px; }.aq-preview-orders span { padding-bottom:9px; border-bottom:1px solid rgba(255,255,255,.08); color:#e4eef6; }.aq-preview-orders b { display:inline-block; width:34px; color:#63d5a0; font-size:9px; font-weight:400; }.aq-preview-orders em { float:right; color:#63d5a0; font-style:normal; font-size:9px; }
/* Typora 式结尾页：品牌图标、描述和双入口按钮。 */
.aq-ending-page {
  position: relative;
  width: 100vw;
  min-height: 100svh;
  margin-left: calc(50% - 50vw);
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: clamp(6rem, 12vw, 10rem) 1.5rem;
  overflow: hidden;
  background: radial-gradient(circle at 18% 24%, rgba(126,200,255,.14), transparent 28%), radial-gradient(circle at 84% 74%, rgba(255,180,84,.13), transparent 30%), linear-gradient(145deg, #081120 0%, #101d36 50%, #070b15 100%);
  color: var(--aq-paper);
}
.aq-ending-page::before { content:""; position:absolute; inset:12% 18%; border:1px solid rgba(126,200,255,.08); border-radius:50%; transform:rotate(-12deg) scaleX(1.4); pointer-events:none; }
.aq-ending-inner { position:relative; z-index:1; width:min(760px,100%); text-align:center; }
.aq-ending-kicker { display:block; margin-bottom:1.25rem; color:var(--aq-teal); font:10px "JetBrains Mono",monospace; letter-spacing:.24em; }
.aq-ending-title { margin:0; color:var(--aq-paper); font:500 clamp(3.2rem,7vw,6.8rem) Fraunces,serif; letter-spacing:-.065em; line-height:.98; }
.aq-ending-offer { display:flex; align-items:center; justify-content:center; gap:1.2rem; margin:clamp(2.8rem,5vw,4.2rem) auto 2.4rem; }
.aq-ending-logo { width:clamp(78px,9vw,108px); height:clamp(78px,9vw,108px); flex:0 0 auto; border:1px solid rgba(126,200,255,.24); border-radius:24%; box-shadow:0 18px 48px rgba(0,0,0,.25),0 0 24px rgba(126,200,255,.08); object-fit:cover; }
.aq-ending-description { max-width:310px; text-align:left; color:#b8c9d8; font:400 clamp(1rem,1.8vw,1.25rem) "Space Grotesk",sans-serif; line-height:1.55; }
.aq-ending-description small { display:block; margin-top:.45rem; color:#7288a0; font:10px "JetBrains Mono",monospace; letter-spacing:.12em; text-transform:uppercase; }
.aq-ending-actions { display:flex; justify-content:center; gap:.9rem; }
.aq-ending-button { position:relative; min-width:148px; padding:.85rem 1.5rem; overflow:hidden; border:1px solid transparent; border-radius:999px; font:500 .9rem "Space Grotesk",sans-serif; text-decoration:none !important; cursor:pointer; transition:transform .28s cubic-bezier(.22,1,.36,1),box-shadow .28s ease,background .28s ease,color .28s ease,border-color .28s ease; }
.aq-ending-button::after { content:""; position:absolute; inset:0; transform:translateX(-120%); background:linear-gradient(105deg,transparent 35%,rgba(255,255,255,.38) 50%,transparent 65%); transition:transform .6s ease; }
.aq-ending-button:hover { transform:translateY(-4px); }.aq-ending-button:hover::after { transform:translateX(120%); }
.aq-ending-button-register { background:#0d1626; color:#eef5fd !important; border-color:rgba(126,200,255,.35); box-shadow:0 12px 28px rgba(0,0,0,.22); }.aq-ending-button-register:hover { background:#19343b; border-color:rgba(126,200,255,.72); box-shadow:0 18px 38px rgba(126,200,255,.12); }
.aq-ending-button-login { background:#eef5fd; color:#0d1626 !important; box-shadow:0 12px 28px rgba(0,0,0,.2); }.aq-ending-button-login:hover { background:#fff; box-shadow:0 18px 38px rgba(126,200,255,.18); }

/* 注册 / 登录毛玻璃弹窗。 */
.aq-auth-overlay { position:fixed; inset:0; z-index:3000; display:none; align-items:center; justify-content:center; padding:1.5rem; background:rgba(2,8,12,.54); backdrop-filter:blur(16px) saturate(.8); -webkit-backdrop-filter:blur(16px) saturate(.8); opacity:0; transition:opacity .3s ease; }
.aq-auth-overlay.is-open { display:flex; opacity:1; }
.aq-auth-backdrop { position:absolute; inset:0; }
.aq-auth-card { position:relative; z-index:1; width:min(430px,100%); padding:2rem; border:1px solid rgba(126,200,255,.3); border-radius:24px; background:linear-gradient(145deg,rgba(25,62,72,.76),rgba(7,18,25,.84)); box-shadow:0 30px 100px rgba(0,0,0,.45),0 0 60px rgba(37,99,235,.12),inset 0 1px rgba(255,255,255,.14); backdrop-filter:blur(28px) saturate(1.15); -webkit-backdrop-filter:blur(28px) saturate(1.15); transform:translateY(18px) scale(.97); transition:transform .38s cubic-bezier(.22,1,.36,1); }
.aq-auth-overlay.is-open .aq-auth-card { transform:translateY(0) scale(1); }
.aq-auth-close { position:absolute; top:1rem; right:1rem; display:flex; align-items:center; justify-content:center; width:2.75rem; height:2.75rem; padding:0; appearance:none; border:1px solid rgba(126,200,255,.28); border-radius:50%; background:rgba(8,24,31,.72); color:#d6e6f4; font:400 1.4rem/1 Arial,sans-serif; cursor:pointer; box-sizing:border-box; transition:background .25s ease,color .25s ease,border-color .25s ease,transform .25s cubic-bezier(.22,1,.36,1),box-shadow .25s ease; }
.aq-auth-close:hover { background:#7ec8ff; border-color:#7ec8ff; color:#081120; transform:rotate(90deg) scale(1.08); box-shadow:0 0 24px rgba(126,200,255,.3); }
.aq-auth-close:active { transform:rotate(90deg) scale(.94); }
.aq-auth-brand { display:flex; align-items:center; gap:.65rem; margin-bottom:1.6rem; color:#eef5fd; font:500 1rem "Space Grotesk",sans-serif; }
.aq-auth-brand img { width:2rem; height:2rem; border-radius:22%; object-fit:cover; }
.aq-auth-tabs { display:grid; grid-template-columns:1fr 1fr; gap:.35rem; padding:.25rem; margin-bottom:1.7rem; border:1px solid rgba(126,200,255,.14); border-radius:999px; background:rgba(0,0,0,.16); }
.aq-auth-tab { padding:.55rem; border:0; border-radius:999px; background:transparent; color:#789094; font:500 .82rem "Space Grotesk",sans-serif; cursor:pointer; transition:background .25s ease,color .25s ease,box-shadow .25s ease; }
.aq-auth-tab.is-active { background:rgba(126,200,255,.16); color:#eef5fd; box-shadow:0 0 18px rgba(126,200,255,.08); }
.aq-auth-panel { display:none; }.aq-auth-panel.is-active { display:block; animation:aqAuthPanelIn .35s ease both; }
@keyframes aqAuthPanelIn { from { opacity:0; transform:translateX(8px); } to { opacity:1; transform:translateX(0); } }
.aq-auth-panel h3 { margin:0 0 .45rem; color:#eef5fd; font:500 1.65rem Fraunces,serif; letter-spacing:-.04em; }.aq-auth-panel p { margin:0 0 1.4rem; color:#9cb2c4; font-size:.82rem; line-height:1.6; }
.aq-auth-field { display:block; margin-top:1rem; color:#d2e0ec; font:500 .82rem "Space Grotesk",sans-serif; letter-spacing:.02em; }.aq-auth-field input { display:block; width:100%; box-sizing:border-box; margin-top:.45rem; padding:.88rem .95rem; border:1px solid rgba(126,200,255,.22); border-radius:11px; outline:none; background:rgba(4,12,17,.48); color:#eef5fd; font: .98rem "Space Grotesk",sans-serif; transition:border-color .25s ease,box-shadow .25s ease,background .25s ease,transform .25s ease; }.aq-auth-field input::placeholder { color:#7288a0; font-size:.92rem; }.aq-auth-field input:focus { border-color:rgba(126,200,255,.78); background:rgba(4,12,17,.7); transform:translateY(-1px); box-shadow:0 0 0 3px rgba(126,200,255,.1),0 0 22px rgba(126,200,255,.08); }
.aq-auth-meta { display:flex; justify-content:flex-end; margin-top:.75rem; }.aq-auth-link { border:0; padding:0; background:transparent; color:#7ec8ff; font-size:.82rem; cursor:pointer; transition:color .2s ease,text-shadow .2s ease; }.aq-auth-link:hover { color:#c0fffb; text-shadow:0 0 12px rgba(126,200,255,.45); }.aq-auth-submit { position:relative; width:100%; margin-top:1.5rem; padding:.9rem 1rem; overflow:hidden; border:0; border-radius:999px; background:linear-gradient(135deg,#7ec8ff,#2563eb); color:#f4f9ff; font:600 .95rem "Space Grotesk",sans-serif; cursor:pointer; box-shadow:0 10px 26px rgba(37,99,235,.32); transition:transform .25s ease,box-shadow .25s ease,background .25s ease; }.aq-auth-submit::after { content:""; position:absolute; inset:0; transform:translateX(-120%); background:linear-gradient(105deg,transparent 35%,rgba(255,255,255,.6) 50%,transparent 65%); transition:transform .55s ease; }.aq-auth-submit:hover { transform:translateY(-3px) scale(1.01); background:linear-gradient(135deg,#9fd6ff,#3b82f6); box-shadow:0 14px 32px rgba(37,99,235,.42); }.aq-auth-submit:active { transform:translateY(0) scale(.98); }.aq-auth-submit:hover::after { transform:translateX(120%); }
.aq-auth-note { margin:1rem 0 0; color:#7288a0; text-align:center; font-size:.72rem; line-height:1.5; }

/* Streamlit 原生认证表单：外观与上面的毛玻璃弹窗一致，输入可提交到 Python。 */
.st-key-aq_auth_triggers { position:absolute !important; width:1px !important; height:1px !important; overflow:hidden !important; opacity:0 !important; pointer-events:none !important; }
.st-key-aq_native_auth_modal { position:fixed !important; inset:0 !important; z-index:3100 !important; display:flex !important; align-items:center !important; justify-content:center !important; padding:1.5rem !important; box-sizing:border-box !important; background:rgba(2,8,12,.58) !important; backdrop-filter:blur(16px) saturate(.82) !important; -webkit-backdrop-filter:blur(16px) saturate(.82) !important; }
.st-key-aq_native_auth_modal > div { width:100% !important; max-width:470px !important; }
.st-key-aq_native_auth_card { width:100% !important; max-height:calc(100svh - 3rem) !important; overflow:auto !important; padding:2rem !important; box-sizing:border-box !important; border:1px solid rgba(126,200,255,.3) !important; border-radius:24px !important; background:linear-gradient(145deg,rgba(25,62,72,.9),rgba(7,18,25,.94)) !important; box-shadow:0 30px 100px rgba(0,0,0,.48),0 0 60px rgba(37,99,235,.14),inset 0 1px rgba(255,255,255,.14) !important; backdrop-filter:blur(28px) saturate(1.15) !important; -webkit-backdrop-filter:blur(28px) saturate(1.15) !important; animation:aqNativeAuthIn .38s cubic-bezier(.22,1,.36,1) both; }
@keyframes aqNativeAuthIn { from { opacity:0; transform:translateY(18px) scale(.97); } to { opacity:1; transform:translateY(0) scale(1); } }
.st-key-aq_native_auth_card [data-testid="stMarkdownContainer"] h3 { margin:0 0 .45rem !important; color:#eef5fd !important; font:500 1.7rem Fraunces,serif !important; letter-spacing:-.04em !important; }
.st-key-aq_native_auth_card [data-testid="stMarkdownContainer"] p { color:#aec2d4 !important; font-size:.9rem !important; line-height:1.6 !important; }
.st-key-aq_native_auth_card [data-testid="stForm"] { padding:0 !important; border:0 !important; background:transparent !important; }
.st-key-aq_native_auth_card [data-testid="stTextInput"] { display:block !important; width:100% !important; margin-top:1rem !important; }
.st-key-aq_native_auth_card [data-testid="stTextInput"] > label,
.st-key-aq_native_auth_card [data-testid="stTextInput"] label { display:block !important; width:100% !important; margin:0 0 .42rem !important; color:#d2e0ec !important; font:500 .84rem "Space Grotesk",sans-serif !important; }
.st-key-aq_native_auth_card [data-testid="stTextInput"] > div,
.st-key-aq_native_auth_card [data-testid="stTextInput"] > label > div:last-child,
.st-key-aq_native_auth_card [data-testid="stTextInput"] [data-baseweb="input"] { display:block !important; width:100% !important; min-width:100% !important; box-sizing:border-box !important; }
.st-key-aq_native_auth_card [data-testid="stTextInput"] [data-baseweb="input"] { min-height:2.9rem !important; border:1px solid rgba(126,200,255,.28) !important; border-radius:11px !important; background:linear-gradient(135deg,rgba(126,200,255,.13),rgba(255,255,255,.075)) !important; background-color:rgba(126,200,255,.1) !important; box-shadow:inset 0 1px rgba(255,255,255,.1),0 8px 24px rgba(0,0,0,.08) !important; transition:border-color .25s ease,box-shadow .25s ease,background .25s ease,transform .25s ease !important; }
.st-key-aq_native_auth_card [data-testid="stTextInput"] [data-baseweb="input"]:focus-within { border-color:rgba(126,200,255,.78) !important; background:rgba(4,12,17,.7) !important; transform:translateY(-1px); box-shadow:0 0 0 3px rgba(126,200,255,.1),0 0 22px rgba(126,200,255,.08) !important; }
.st-key-aq_native_auth_card [data-testid="stTextInput"] input { display:block !important; width:100% !important; min-height:2.9rem !important; padding:.75rem .9rem !important; box-sizing:border-box !important; border:0 !important; outline:0 !important; background:linear-gradient(135deg,rgba(126,200,255,.08),rgba(255,255,255,.035)) !important; background-color:rgba(126,200,255,.06) !important; color:#eef5fd !important; -webkit-text-fill-color:#eef5fd !important; font:400 1rem "Space Grotesk",sans-serif !important; }
.st-key-aq_native_auth_card [data-testid="stTextInput"] input:-webkit-autofill,
.st-key-aq_native_auth_card [data-testid="stTextInput"] input:-webkit-autofill:hover,
.st-key-aq_native_auth_card [data-testid="stTextInput"] input:-webkit-autofill:focus { -webkit-text-fill-color:#eef5fd !important; -webkit-box-shadow:0 0 0 1000px rgba(32,72,140,.72) inset !important; box-shadow:0 0 0 1000px rgba(32,72,140,.72) inset !important; }
.st-key-aq_native_auth_card [data-testid="stTextInput"] input::placeholder { color:#7288a0 !important; opacity:1 !important; font-size:.92rem !important; }
.st-key-aq_native_auth_card [data-testid="stButton"] button { min-height:2.7rem !important; border-radius:999px !important; font-size:.9rem !important; transition:transform .25s ease,box-shadow .25s ease,background .25s ease,border-color .25s ease !important; }
.st-key-aq_native_auth_card [data-testid="stButton"] button:hover { transform:translateY(-3px) !important; box-shadow:0 12px 28px rgba(126,200,255,.16) !important; }
.st-key-aq_native_auth_card [data-testid="stButton"] button:active { transform:translateY(0) scale(.97) !important; }
.st-key-aq_native_auth_card [data-testid="stButton"] button[kind="primary"] { background:#eef5fd !important; border-color:#eef5fd !important; color:#0d1626 !important; }
.st-key-aq_native_auth_card [data-testid="stButton"] button[kind="primary"] * { color:#0d1626 !important; }
.st-key-aq_native_auth_card [data-testid="stFormSubmitButton"] button { background:linear-gradient(135deg,#7ec8ff,#2563eb) !important; border:0 !important; color:#f4f9ff !important; font-weight:600 !important; box-shadow:0 10px 26px rgba(37,99,235,.32) !important; }
.st-key-aq_native_auth_card [data-testid="stFormSubmitButton"] button * { color:#f4f9ff !important; }
.st-key-aq_native_auth_card [data-testid="stFormSubmitButton"] button:hover { background:linear-gradient(135deg,#9fd6ff,#3b82f6) !important; box-shadow:0 14px 32px rgba(37,99,235,.42) !important; }
/* 登录 / 注册切换：胶囊分段控件，与首页顶部语言切换同一语言 */
.st-key-aq_native_auth_card [data-testid="stHorizontalBlock"] { gap:.4rem !important; }
.st-key-aq_native_auth_card [data-testid="stButton"] button[kind="primary"] { background:rgba(126,200,255,.16) !important; border:1px solid rgba(126,200,255,.55) !important; color:#eef5fd !important; box-shadow:0 0 18px rgba(126,200,255,.1) !important; }
.st-key-aq_native_auth_card [data-testid="stButton"] button[kind="primary"] * { color:#eef5fd !important; }
.st-key-aq_native_auth_card [data-testid="stButton"] button[kind="secondary"] { background:transparent !important; border:1px solid rgba(126,200,255,.16) !important; color:#8ca3b8 !important; }
.st-key-aq_native_auth_card [data-testid="stButton"] button[kind="secondary"]:hover { border-color:rgba(126,200,255,.55) !important; color:#eef5fd !important; }
.st-key-aq_native_auth_close button { min-width:2rem !important; width:2rem !important; height:2rem !important; padding:0 !important; border:1px solid rgba(126,200,255,.3) !important; border-radius:50% !important; background:rgba(8,24,31,.72) !important; color:#d6e6f4 !important; font:600 1.15rem/1 Arial,sans-serif !important; line-height:1 !important; }
.st-key-aq_native_auth_close button:hover { background:#7ec8ff !important; border-color:#7ec8ff !important; color:#081120 !important; transform:rotate(90deg) scale(1.12) !important; box-shadow:0 0 20px rgba(126,200,255,.28) !important; }

.aq-guide-card-title {
  display: flex;
  align-items: center;
  gap: .55rem;
  min-height: 2.2rem;
  color: var(--aq-paper);
  font: 500 1.05rem "Space Grotesk", sans-serif;
}
.aq-guide-card-icon {
  display: inline-flex;
  width: 1.35rem;
  height: 1.35rem;
  align-items: center;
  justify-content: center;
  color: var(--aq-ember);
  font-size: .95rem;
  filter: saturate(.9);
}
.st-key-aq_sec_guide [data-testid="stCaptionContainer"] {
  min-height: 3.4rem !important;
  margin-top: .9rem !important;
  color: var(--aq-muted) !important;
  font-size: .86rem !important;
  line-height: 1.65 !important;
}
.st-key-aq_sec_guide [data-testid="stButton"] { margin-top: auto !important; }
.st-key-aq_sec_guide [data-testid="stButton"] button {
  min-height: 2.35rem !important;
  border: 1px solid rgba(126,200,255,.2) !important;
  border-radius: 999px !important;
  background: transparent !important;
  color: #b8c9d8 !important;
  font-size: .78rem !important;
  transition: color .25s ease, border-color .25s ease, background .25s ease, transform .25s ease !important;
}
.st-key-aq_sec_guide [data-testid="stButton"] button:hover {
  border-color: rgba(126,200,255,.7) !important;
  background: rgba(126,200,255,.1) !important;
  color: var(--aq-paper) !important;
  transform: translateY(-2px) !important;
}

@media (prefers-reduced-motion: reduce) {
  .aq-product-overview::after, .aq-workflow-section::after,
  .st-key-aq_sec_guide::after, .st-key-aq_sec_modules::after,
  .st-key-aq_sec_status::after, .st-key-aq_sec_runs::after,
  .st-key-aq_sec_guide [class*="st-key-aq_guide_step_"],
  .st-key-aq_sec_modules .aq-module-card { animation: none !important; }
}
@media (max-width: 800px) {
  .aq-product-overview,
  .aq-workflow-section,
  .st-key-aq_sec_guide,
  .st-key-aq_sec_modules,
  .st-key-aq_sec_status,
  .st-key-aq_sec_runs,
  .st-key-aq_sec_detail { padding-left: 1.1rem !important; padding-right: 1.1rem !important; }
  .aq-product-grid { grid-template-columns: 1fr !important; }
  .aq-product-card { min-height: 210px !important; }
  .aq-flow-grid { grid-template-columns: 1fr !important; }
  .aq-workflow { border-radius: 18px !important; }
  .st-key-aq_sec_guide [data-testid="stHorizontalBlock"] { grid-template-columns: 1fr 1fr !important; }
  .st-key-aq_sec_guide [class*="st-key-aq_guide_step_"] { min-height: 320px !important; height: 320px !important; }
  .aq-launch-content { padding-left: .5rem; padding-right: .5rem; }
  .aq-launch-title { font-size: clamp(3.5rem, 16vw, 5.4rem); }
  .aq-launch-typing { letter-spacing: 2px; }
  .aq-launch-phrase { width: 50ch; }
  .aq-ending-offer { align-items: flex-start; }
  .aq-ending-logo { width: 76px; height: 76px; }
  .aq-ending-description { font-size: 1rem; }
}
@media (max-width: 520px) {
  .st-key-aq_sec_guide [data-testid="stHorizontalBlock"] { grid-template-columns: 1fr !important; }
  .st-key-aq_sec_guide [class*="st-key-aq_guide_step_"] { min-height: 290px !important; height: 290px !important; }
  .aq-ending-offer { flex-direction: column; align-items: center; gap: 1rem; }
  .aq-ending-description { text-align: center; }
  .aq-ending-actions { flex-direction: column; align-items: stretch; max-width: 220px; margin: 0 auto; }
  .aq-ending-button { width: 100%; box-sizing: border-box; }
}

</style>
"""

# ── 中英文案（主页范围内） ─────────────────────────────────────────
_TEXT: dict[str, dict[str, object]] = {
    "zh": {
        "eyebrow": "FELLOWQUANT / AI-NATIVE RESEARCH WORKBENCH",
        "title": "研究交易，",
        "accent": "一站完成。",
        "subtitle": "从数据、因子和策略，到回测、智能体研究与模拟交易，FellowQuant 把完整的量化研究闭环放进一个本地优先的工作台。",
        "badge_local": "本地优先 · 数据私有",
        "ready_pill": "● 已具备回测条件",
        "warn_pill": "● 首次准备尚未完成",
        "cta_backtest": "进入回测",
        "cta_agent": "智能体分析台",
        "cta_data": "数据管理",
        "cta_pool": "股票池管理",
        "term_comment": "# 数据 → 因子 → 策略 → 多智能体研究 → 风控",
        "term_decision": "决策完成：买入 · 目标仓位 60.0%",
        "term_backtest": "回测完成：年化 18.2% · 最大回撤 -8.4%",
        "scroll_hint": "向下滚动",
        "sec_guide": "新手上路",
        "sec_guide_hint": "按顺序完成六步，即可从数据走到模拟交易；高级参数在各页面内折叠隐藏",
        "sec_modules": "模块直达",
        "sec_modules_hint": "从任意卡片进入对应工作台",
        "open": "打开",
        "sec_status": "平台状态",
        "sec_status_hint": "本地配置与数据检查结果",
        "status_note": "平台会自动检查本地配置与数据，<br/>"
        "并按下方顺序引导你完成首次准备，<br/>无需手工编辑配置文件。",
        "sec_runs": "最近运行",
        "sec_runs_hint": "最近一次成功或失败的回测记录",
        "no_runs": "暂无回测记录，先从「单次回测与复盘」运行一次吧。",
        "goto_backtest": "去运行一次回测",
        "all_runs": "查看全部记录",
        "trouble_title": "环境检查明细与排障",
        "trouble_body": """
- **股票池为空**：前往「股票池管理」，输入六位股票代码并保存。
- **没有股票行情**：前往「数据管理」，勾选「更新配置股票池行情」。
- **历史天数不足**：把数据更新的开始日期向前调整，再次更新。
- **证券主表缺失**：仍可通过代码添加股票，但按名称搜索前需要更新证券主表。
- **网络更新失败**：检查网络或代理后重试；已经成功的数据不会被删除。
""",
        "ready_footer": "已具备回测条件",
        "not_ready_footer": "数据就绪后可运行",
        "pool_footer_ok": "已配置 {n} 只股票",
        "pool_footer_empty": "尚未添加股票",
        "data_footer": "覆盖 {ok}/{total} 只",
    },
    "en": {
        "eyebrow": "FELLOWQUANT / AI-NATIVE RESEARCH WORKBENCH",
        "title": "Research to execution,",
        "accent": "in one place.",
        "subtitle": "From data, factors and strategies to backtesting, multi-agent research and paper trading — FellowQuant brings the full quantitative workflow into one local-first workbench.",
        "badge_local": "Local-first · Private data",
        "ready_pill": "● Ready for backtest",
        "warn_pill": "● Setup incomplete",
        "cta_backtest": "Run Backtest",
        "cta_agent": "Agent Lab",
        "cta_data": "Data Management",
        "cta_pool": "Universe",
        "term_comment": "# data → factors → strategy → agent research → risk",
        "term_decision": "Decision: BUY · target position 60.0%",
        "term_backtest": "Backtest done: 18.2% ann. · -8.4% max drawdown",
        "scroll_hint": "Scroll down",
        "sec_guide": "Getting Started",
        "sec_guide_hint": "Follow the six steps from data to paper trading",
        "sec_modules": "Modules",
        "sec_modules_hint": "Jump into any workbench",
        "open": "Open",
        "sec_status": "Platform Status",
        "sec_status_hint": "Local configuration & data checks",
        "status_note": "The platform checks local configuration and data automatically,<br/>"
        "and guides you through first-time setup —<br/>no config files to edit.",
        "sec_runs": "Recent Runs",
        "sec_runs_hint": "Latest backtest records, success or failure",
        "no_runs": "No backtest records yet — run one from Backtest & Review.",
        "goto_backtest": "Run a backtest",
        "all_runs": "View all records",
        "trouble_title": "Environment checks & troubleshooting",
        "trouble_body": """
- **Empty universe**: go to Universe and save six-digit symbols.
- **No market data**: go to Data Management and enable universe bar updates.
- **Insufficient history**: move the update start date earlier and update again.
- **Missing security master**: symbols still work; update the master table for name search.
- **Network failures**: check your network or proxy; completed data is never deleted.
""",
        "ready_footer": "Ready for backtest",
        "not_ready_footer": "Available once data is ready",
        "pool_footer_ok": "{n} symbols configured",
        "pool_footer_empty": "No symbols yet",
        "data_footer": "Coverage {ok}/{total}",
    },
}

_MODULES: dict[str, list[tuple[str, str, str, str, str]]] = {
    # icon, title, desc, page, footer 模板键或原文
    "zh": [
        ("hub", "策略创作中心",
         "模板、积木、自然语言、Python 四种方式创建策略，统一注册与回测。",
         "pages/0_strategy_hub.py", "统一入口"),
        ("candlestick_chart", "单次回测与复盘",
         "选择策略并运行一次完整回测，查看收益、回撤与可信度审计。", "home.py", ""),
        ("widgets", "零代码策略工作台",
         "以声明式参数与规则搭建策略，自动生成参数表单，无需编写代码。",
         "pages/7_strategy_studio.py", "零代码 · 参数化"),
        ("code", "自定义策略（Python）",
         "在网页中编写或上传 Python 策略，自动解析参数并生成表单。",
         "pages/8_custom_strategy.py", "Python 进阶"),
        ("psychology", "智能体分析台",
         "LLM 多智能体协作完成行情解读、因子研究与交易分析。",
         "pages/8_agent_lab.py", "多智能体研究"),
        ("science", "因子研究室",
         "内置量价因子的 IC、分层收益与稳定性评估，支持多因子合成选股。",
         "pages/9_factor_lab.py", "IC · 分层 · 合成"),
        ("chat", "自然语言建策略",
         "用一句话描述策略，大模型转成结构化规则，确认后保存。",
         "pages/10_nl_strategy.py", "DeepSeek / Kimi / Ollama"),
        ("database", "数据管理",
         "下载证券主表、股票日线与基准行情，检查覆盖率和数据质量。",
         "pages/1_data_management.py", ""),
        ("tune", "参数优化与稳健性验证",
         "网格 / 随机搜索参数组合，并用样本外数据验证策略稳健性。",
         "pages/2_research.py", "搜索 + 样本外验证"),
        ("history", "回测记录库",
         "统一管理单次回测、参数优化与样本外验证结果，支持比较。",
         "pages/6_run_library.py", "历史记录 · 对比"),
        ("shield", "风险管理",
         "事件化风控检查与决策记录，为模拟交易提供前置拦截。",
         "pages/3_risk_management.py", "事件检查 · 决策"),
        ("account_balance", "模拟交易",
         "以真实行情节奏模拟下单，追踪账户净值与交易明细。",
         "pages/4_paper_trading.py", "paper trading"),
        ("list_alt", "股票池管理",
         "添加股票、配置回测区间与最小历史天数，管理研究标的。",
         "pages/5_universe_management.py", ""),
    ],
    "en": [
        ("hub", "Strategy Hub",
         "Templates, blocks, natural language or Python — one registration flow.",
         "pages/0_strategy_hub.py", "Unified entry"),
        ("candlestick_chart", "Backtest & Review",
         "Run a full backtest with a strategy; inspect returns, drawdowns and audits.",
         "home.py", ""),
        ("widgets", "No-Code Strategy Studio",
         "Build strategies declaratively with auto-generated parameter forms.",
         "pages/7_strategy_studio.py", "No-code · Parametric"),
        ("code", "Custom Strategy (Python)",
         "Write or upload Python strategies in the browser with parsed parameters.",
         "pages/8_custom_strategy.py", "Advanced Python"),
        ("psychology", "Agent Lab",
         "LLM multi-agent research: market reading, factor study, trade analysis.",
         "pages/8_agent_lab.py", "Multi-agent research"),
        ("science", "Factor Lab",
         "IC, quantile returns and stability for built-in factors; composite scoring.",
         "pages/9_factor_lab.py", "IC · Groups · Composite"),
        ("chat", "NL Strategy Builder",
         "Describe a strategy in one sentence; the LLM drafts structured rules.",
         "pages/10_nl_strategy.py", "DeepSeek / Kimi / Ollama"),
        ("database", "Data Management",
         "Fetch security master, daily bars and benchmarks; check coverage & quality.",
         "pages/1_data_management.py", ""),
        ("tune", "Optimization & Robustness",
         "Grid / random parameter search with out-of-sample validation.",
         "pages/2_research.py", "Search + OOS validation"),
        ("history", "Run Library",
         "Manage backtests, optimizations and OOS results; compare runs.",
         "pages/6_run_library.py", "History · Compare"),
        ("shield", "Risk Management",
         "Event-based risk checks and decisions guarding paper trading.",
         "pages/3_risk_management.py", "Event checks · Decisions"),
        ("account_balance", "Paper Trading",
         "Simulated orders at real market pace; track equity and fills.",
         "pages/4_paper_trading.py", "paper trading"),
        ("list_alt", "Universe",
         "Add symbols, configure backtest range and minimum history.",
         "pages/5_universe_management.py", ""),
    ],
}


def _lang() -> str:
    return st.session_state.get("aq_lang", "zh")


def _t(key: str) -> str:
    return str(_TEXT[_lang()][key])


def _check_state(report, item: str) -> str:
    """把某个检查项映射成 Harness 状态圆点。"""
    for check in report.checks:
        if check.item == item:
            return _STATE_TO_DOT.get(check.status, "idle")
    return "idle"


def _render_stickybar() -> None:
    """顶部悬浮导航条：网页名与语言切换。

    页面顶端为透明状态（贴在网页顶部）；向下滚动时背景变为毛玻璃。
    GitHub 与账户入口由独立的右上角操作组持续展示。
    """
    with st.container(key="aq_stickybar"):
        brand_col, lang_col = st.columns([1, 1])
        with brand_col:
            st.markdown(
                topbar_html("FellowQuant"),
                unsafe_allow_html=True,
            )
        with lang_col:
            if "aq_language" not in st.session_state:
                st.session_state["aq_language"] = "中文" if _lang() == "zh" else "EN"
            choice = st.segmented_control(
                "Language / 语言",
                ["中文", "EN"],
                key="aq_language",
                label_visibility="collapsed",
            )
    if choice:
        lang = "zh" if choice == "中文" else "en"
        if lang != _lang():
            st.session_state["aq_lang"] = lang
            st.rerun()


def _logout_authenticated_user() -> None:
    """清除当前 Streamlit 会话中的认证状态。"""
    st.session_state["aq_authenticated_user"] = None
    st.session_state.pop("aq_auth_mode", None)


def _render_account_status() -> None:
    """在欢迎页右上角显示 GitHub 与当前账户操作。"""
    username = st.session_state.get("aq_authenticated_user")
    with st.container(key="aq_welcome_actions"):
        github_col, account_col = st.columns(
            [1, 1], gap="small", vertical_alignment="center"
        )
        with github_col:
            with st.container(key="aq_welcome_github"):
                st.markdown(
                    github_link_html("https://github.com/FelixZhang028/AlphaQuant"),
                    unsafe_allow_html=True,
                )
        with account_col:
            with st.container(key="aq_welcome_account"):
                if username:
                    with st.popover(str(username), icon=":material/account_circle:"):
                        account_label = "当前账户" if _lang() == "zh" else "Signed in as"
                        st.caption(f"{account_label}: {username}")
                        if st.button(
                            "进入工作台" if _lang() == "zh" else "Open workbench",
                            key="aq_account_open_workbench",
                            icon=":material/space_dashboard:",
                            width="stretch",
                        ):
                            st.switch_page("home.py")
                        if st.button(
                            "退出登录" if _lang() == "zh" else "Log out",
                            key="aq_account_logout",
                            icon=":material/logout:",
                            width="stretch",
                        ):
                            _logout_authenticated_user()
                            st.rerun()
                elif st.button(
                    "登录 / 注册" if _lang() == "zh" else "Log in / Register",
                    key="aq_account_login",
                    icon=":material/login:",
                ):
                    st.session_state["aq_auth_mode"] = "login"
                    st.rerun()


def _render_hero(report) -> None:
    """Typora feature 风格 hero：左侧研究优势，右侧固定 Mac 编辑器。"""
    if _lang() == "zh":
        highlights = (
            ("✦", "专注研究：数据、因子与策略统一管理"),
            ("↗", "实时验证：回测结果与风险检查同步呈现"),
            ("◉", "所见即所得：每一次实验都可复用、可审计"),
        )
        terminal_scenes = (
            (
                '<div class="aq-editor-heading">研究，从一个清晰的问题开始。</div>',
                '<p class="aq-editor-copy">FellowQuant 将复杂的量化流程整理成一个可持续推进的研究工作台。</p>',
                '<ul class="aq-editor-list"><li>数据、因子与策略统一管理</li><li>回测与智能体研究无缝衔接</li></ul>',
            ),
            (
                '<div class="aq-editor-heading">让每一次实验都留下上下文。</div>',
                '<p class="aq-editor-copy">从假设、参数到结果，研究过程被完整保留，方便复盘与比较。</p>',
                '<ul class="aq-editor-list"><li>保留策略上下文</li><li>快速对比不同研究结果</li></ul>',
            ),
            (
                '<div class="aq-editor-heading">从回测走向更有把握的决策。</div>',
                '<p class="aq-editor-copy">把风险检查前置，在模拟交易前逐步验证每一个判断。</p>',
                '<ul class="aq-editor-list"><li>风险检查前置</li><li>结果与运行记录统一沉淀</li></ul>',
            ),
        )
        terminal_title = "FellowQuant / Research note"
    else:
        highlights = (
            ("✦", "Focused research: data, factors and strategies in one place"),
            ("↗", "Live validation: backtests and risk checks stay in view"),
            ("◉", "Readable results: every experiment is reusable and auditable"),
        )
        terminal_scenes = (
            (
                '<div class="aq-editor-heading">Research starts with a clear question.</div>',
                '<p class="aq-editor-copy">FellowQuant turns a complex quant workflow into one research workbench you can keep building on.</p>',
                '<ul class="aq-editor-list"><li>Manage data, factors and strategies together</li><li>Connect backtests with agent research</li></ul>',
            ),
            (
                '<div class="aq-editor-heading">Keep the context behind every experiment.</div>',
                '<p class="aq-editor-copy">From hypothesis and parameters to results, the full research trail stays ready for review.</p>',
                '<ul class="aq-editor-list"><li>Preserve strategy context</li><li>Compare research results quickly</li></ul>',
            ),
            (
                '<div class="aq-editor-heading">Move from backtests to confident decisions.</div>',
                '<p class="aq-editor-copy">Put risk checks first and validate each decision before paper trading.</p>',
                '<ul class="aq-editor-list"><li>Surface risk checks early</li><li>Keep results and run history together</li></ul>',
            ),
        )
        terminal_title = "FellowQuant / Research note"
    render_hero(
        _t("title"),
        _t("subtitle"),
        accent=_t("accent"),
        badge=_t("badge_local"),
        eyebrow=_t("eyebrow"),
        terminal_scenes=terminal_scenes,
        terminal_title=terminal_title,
        highlights=highlights,
    )


def _render_launch_splash() -> None:
    """渲染首页第一屏：Typora 式居中品牌标题与循环打字文案。"""
    st.markdown(
        """
<section class="aq-launch-splash" aria-label="FellowQuant opening screen">
  <div class="aq-launch-content">
    <h1 class="aq-launch-title">FellowQuant</h1>
    <div class="aq-launch-typing" aria-label="AI-NATIVE RESEARCH WORKBENCH">
      <span>/*&nbsp;</span>
      <span class="aq-launch-phrase">AI-NATIVE RESEARCH WORKBENCH</span>
      <span>&nbsp;*/</span>
      <span class="aq-launch-cursor" aria-hidden="true"></span>
    </div>
  </div>
  <a class="aq-launch-scroll" href="#aq-welcome-start" aria-label="Scroll to FellowQuant welcome page">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 9.5 12 16l7-6.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
  </a>
</section>
<div id="aq-welcome-start" class="aq-welcome-anchor" aria-hidden="true"></div>
""",
        unsafe_allow_html=True,
    )


def _render_particle_background() -> None:
    """渲染低开销的鼠标交互粒子背景。"""
    with st.container(key="aq_particle_bg"):
        javascript_html(_PARTICLE_BACKGROUND_HTML)


def _render_product_overview() -> None:
    """Typora 风格的功能展示页：每项能力用一个 Mac 窗口预览。"""
    if _lang() == "zh":
        kicker = "01 / THE SYSTEM"
        title = "简单，却足够强大。"
        intro = "FellowQuant 整合数据、策略、回测与智能分析，打造开箱即用的量化研究工作台。"
        features = [
            ("01", "数据管理", "统一维护股票池、证券主表、行情与基准数据。", "Data / workspace", "data"),
            ("02", "策略实验室", "用模板、零代码、Python 或自然语言快速构建策略。", "Strategy / lab", "strategy"),
            ("03", "单次回测", "查看收益、回撤、持仓与交易明细，让结果可解释。", "Backtest / review", "backtest"),
            ("04", "智能分析台", "让多智能体协作完成市场、因子与风险分析。", "Agents / research", "agent"),
            ("05", "优化与稳健性", "通过参数搜索和样本外验证，检查策略是否可靠。", "Optimize / validate", "optimize"),
            ("06", "模拟交易", "在真实市场节奏下观察订单、资金与组合变化。", "Paper / trading", "paper"),
        ]
    else:
        kicker = "01 / THE SYSTEM"
        title = "Simple, yet powerful."
        intro = "From data preparation to strategy validation, FellowQuant brings the essential tools of quantitative research into one coherent workbench."
        features = [
            ("01", "Data Management", "Keep universes, security master, market data and benchmarks in one place.", "Data / workspace", "data"),
            ("02", "Strategy Lab", "Build strategies with templates, no-code blocks, Python or natural language.", "Strategy / lab", "strategy"),
            ("03", "Backtest & Review", "Inspect returns, drawdowns, positions and trades with clear explanations.", "Backtest / review", "backtest"),
            ("04", "Agent Lab", "Let multiple agents collaborate on market, factor and risk analysis.", "Agents / research", "agent"),
            ("05", "Optimization", "Search parameters and validate robustness with out-of-sample testing.", "Optimize / validate", "optimize"),
            ("06", "Paper Trading", "Observe orders, capital and portfolio changes at a real market pace.", "Paper / trading", "paper"),
        ]

    previews = {
        "data": '<div class="aq-mini-row"><i></i><b>Universe</b><span>600519&nbsp;&nbsp;000001&nbsp;&nbsp;601318</span></div><div class="aq-mini-chart bars"><em></em><em></em><em></em><em></em><em></em><em></em></div><div class="aq-mini-status">● 12,482 symbols synced</div>',
        "strategy": '<div class="aq-mini-code"><span>def</span> momentum(data):</div><div class="aq-mini-code">  signal = <strong>rank</strong>(returns)</div><div class="aq-mini-code">  <span>return</span> signal &gt; 0.65</div><div class="aq-mini-pill">PARAMETRIC STRATEGY</div>',
        "backtest": '<div class="aq-mini-metrics"><b>18.2%</b><span>annualized return</span><b>-8.4%</b><span>max drawdown</span></div><div class="aq-mini-chart line"><em></em><em></em><em></em><em></em><em></em></div>',
        "agent": '<div class="aq-mini-agent"><i>◉</i><span>Market Analyst</span><b>ready</b></div><div class="aq-mini-agent"><i>◇</i><span>Risk Analyst</span><b>ready</b></div><div class="aq-mini-agent"><i>✦</i><span>Research Debate</span><b>running</b></div>',
        "optimize": '<div class="aq-mini-grid"><b>Sharpe</b><b>Return</b><b>Drawdown</b><span>1.84</span><span>21.6%</span><span>-9.1%</span><span>1.42</span><span>18.2%</span><span>-8.4%</span></div><div class="aq-mini-status">● OOS validation passed</div>',
        "paper": '<div class="aq-mini-order"><span>BUY</span><b>600519</b><em>100 shares</em><strong>filled</strong></div><div class="aq-mini-order"><span>SELL</span><b>000001</b><em>200 shares</em><strong>filled</strong></div><div class="aq-mini-status">Portfolio value&nbsp; ¥1,024,680</div>',
    }
    features_html = "".join(
        f'<article class="aq-feature-slide" data-feature-index="{position}"><div class="aq-feature-window"><div class="aq-feature-bar"><span class="r"></span><span class="y"></span><span class="g"></span><small>{label}</small></div><div class="aq-feature-body aq-feature-{kind}">{previews[kind]}</div></div><p>{body}</p></article>'
        for position, (index, heading, body, label, kind) in enumerate(features)
    )
    feature_nav_html = "".join(
        f'<button class="aq-feature-tab{" is-active" if position == 0 else ""}" data-feature-target="{position}" onclick="window.aqFeatureShow && window.aqFeatureShow({position})"><span>{index}</span>{heading}</button>'
        for position, (index, heading, _body, _label, _kind) in enumerate(features)
    )
    carousel_html = (
        """<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
        :root{color-scheme:dark}html,body{margin:0;background:transparent;color:#eef5fd;font-family:Arial,sans-serif}*{box-sizing:border-box}
        .tabs{width:min(980px,100%);margin:0 auto 22px;display:flex;justify-content:center;gap:clamp(16px,3vw,48px);border-bottom:1px solid rgba(126,200,255,.16)}
        button{position:relative;padding:0 0 12px;border:0;background:transparent;color:#7288a0;font:500 clamp(13px,1.2vw,16px) Arial,sans-serif;cursor:pointer;white-space:nowrap;transition:color .25s,transform .25s}button span{display:block;margin-bottom:5px;color:#ffb454;font:600 12px monospace;letter-spacing:.12em}button:after{content:"";position:absolute;left:0;right:0;bottom:-1px;height:2px;background:#7ec8ff;transform:scaleX(0);transition:transform .3s}button:hover,button.active,button.is-active{color:#eef5fd;transform:translateY(-2px)}button.active:after,button.is-active:after{transform:scaleX(1)}
        .stage{position:relative;width:min(860px,100%);height:560px;margin:auto;overflow:hidden}.slide{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;opacity:0;pointer-events:none;transform:translateX(112%);transition:transform .55s cubic-bezier(.22,1,.36,1),opacity .42s ease}.stage.fast .slide{transition-duration:.16s}.slide:first-child:not([data-state]){opacity:1;transform:translateX(0);pointer-events:auto}.slide[data-state=active]{opacity:1;transform:translateX(0);pointer-events:auto}.slide[data-state=past]{opacity:0;transform:translateX(-112%)}.slide[data-state=next]{opacity:0;transform:translateX(112%)}
        .window{width:min(560px,100%);height:460px;overflow:hidden;border:1px solid rgba(126,200,255,.3);border-radius:10px;background:linear-gradient(145deg,rgba(27,43,49,.98),rgba(5,12,17,.98));box-shadow:0 18px 45px rgba(0,0,0,.3)}.bar{height:34px;display:flex;align-items:center;gap:5px;padding:0 10px;background:linear-gradient(#22345a,#16223c);border-bottom:1px solid rgba(126,200,255,.14)}.bar i{width:8px;height:8px;border-radius:50%;display:block}.bar .r{background:#ff5f57}.bar .y{background:#febc2e}.bar .g{background:#28c840}.bar small{margin-left:8px;color:#8da4ba;font:10px monospace}.body{height:426px;padding:24px 20px;color:#b8c9d8;font:11px monospace}.slide>p{max-width:560px;margin:14px 0 0;color:#a8b8c8;text-align:center;font-size:14px;line-height:1.6}
        .row{display:flex;gap:8px;align-items:center;margin-bottom:24px}.row i{width:7px;height:7px;border-radius:50%;background:#7ec8ff}.row b{color:#eef5fb}.row span{color:#7f97ae;font-size:9px}.chart{display:flex;align-items:end;gap:8px;height:110px;padding:0 5px;border-bottom:1px solid rgba(126,200,255,.18)}.chart em{display:block;width:13%;border-radius:3px 3px 0 0;background:linear-gradient(#7ec8ff,#2563eb)}.chart em:nth-child(1){height:35%}.chart em:nth-child(2){height:52%}.chart em:nth-child(3){height:44%}.chart em:nth-child(4){height:70%}.chart em:nth-child(5){height:58%}.chart em:nth-child(6){height:86%}.status{margin-top:20px;color:#63d5a0;font-size:10px}.code{line-height:2.25;color:#aec2d4}.code span{color:#ffcf9e}.code strong{color:#7ec8ff}.pill{margin-top:18px;color:#ffd27a;font-size:9px;letter-spacing:.12em}.metrics{display:grid;grid-template-columns:auto 1fr;column-gap:12px;align-items:baseline}.metrics b{color:#eef5fd;font-size:20px}.metrics span{color:#7f97ae;font-size:9px}.agent{display:flex;align-items:center;gap:10px;height:48px;border-bottom:1px solid rgba(255,255,255,.07)}.agent i{color:#7ec8ff;font-style:normal;font-size:16px}.agent span{flex:1;color:#e4eef6}.agent b{color:#63d5a0;font-size:9px;font-weight:400}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;color:#8da4ba}.grid b{color:#7ec8ff;font-size:9px}.grid span{color:#eef5fb}.order{display:grid;grid-template-columns:42px 1fr 1fr;align-items:center;height:50px;border-bottom:1px solid rgba(255,255,255,.07)}.order span{color:#63d5a0;font-size:9px}.order b{color:#eef5fb}.order em{color:#8da4ba;font-style:normal;font-size:9px}.order strong{grid-column:3;color:#63d5a0;font-size:9px;font-weight:400;text-align:right}@media(max-width:600px){.tabs{justify-content:flex-start;overflow-x:auto;gap:22px}.stage{height:340px}.window{height:260px}.bar{height:32px}.body{height:228px;padding:20px 16px}.chart{height:84px}.agent{height:42px}.order{height:44px}.slide>p{padding:0 10px}}
        </style></head><body><nav class="tabs">"""
        + feature_nav_html.replace("aq-feature-tab", "tab")
        + """</nav><main class="stage">"""
        + features_html.replace("aq-feature-slide", "slide").replace("aq-feature-window", "window").replace("aq-feature-bar", "bar").replace("aq-feature-body", "body")
         + """</main><script>
         (() => {
           let timer = 0;
           const getScope = () => document.querySelector('.st-key-aq_product_overview_wrap') || document;
           window.aqFeatureShow = (target) => {
             const scope = getScope();
             if (!scope) return;
             const tabs = [...scope.querySelectorAll('.tab')];
             const slides = [...scope.querySelectorAll('.slide')];
             const currentTab = scope.querySelector('.tab.active, .tab.is-active');
             const current = currentTab ? Number(currentTab.dataset.featureTarget || tabs.indexOf(currentTab)) : 0;
             const next = Math.max(0, Math.min(Number(target), slides.length - 1));
             const fast = Math.abs(next - current) > 1;
             clearTimeout(timer);
             slides.forEach((slide, i) => { slide.dataset.state = i === next ? 'active' : (i < next ? 'past' : 'next'); });
             tabs.forEach((tab, i) => { tab.classList.toggle('active', i === next); tab.classList.toggle('is-active', i === next); });
             scope.querySelector('.stage')?.classList.toggle('fast', fast);
             if (fast) timer = window.setTimeout(() => scope.querySelector('.stage')?.classList.remove('fast'), 180);
           };
           if (!window.aqFeatureDelegated) {
             document.addEventListener('click', (event) => {
               const tab = event.target.closest?.('.st-key-aq_product_overview_wrap .tab');
               if (tab) window.aqFeatureShow(Number(tab.dataset.featureTarget));
             });
             window.aqFeatureDelegated = true;
           }
           window.aqFeatureShow(0);
         })();
          </script></body></html>"""
    ).replace(
        ".stage{height:340px}.window{height:260px}.bar{height:32px}.body{height:228px}",
        ".stage{height:470px}.window{height:380px}.bar{height:32px}.body{height:348px}",
    )
    with st.container(key="aq_product_overview_wrap"):
        st.markdown(
            f'<div class="aq-overview-heading"><span class="aq-section-kicker">{kicker}</span><h2>{title}</h2><p>{intro}</p></div>',
            unsafe_allow_html=True,
        )
        javascript_html(carousel_html, fallback_height=620)


def _render_guide(report, config_path: str) -> None:
    """Typora 风格的 02 / RESEARCH LOOP：六步流程，两行三列展示。"""

    has_strategies = False
    has_runs = False
    has_paper = False
    try:
        backtests = BacktestService(config_path)
        has_strategies = bool(StrategyStudioService(backtests).store.list())
        has_runs = bool(backtests.run_store.list_records())
        has_paper = bool(PaperTradingService(backtests).list_accounts())
    except Exception:  # noqa: BLE001 - 引导信息缺失不应影响主页
        pass

    steps = build_guide_steps(
        configured_symbols=report.configured_symbols,
        symbols_with_sufficient_history=report.symbols_with_sufficient_history,
        has_strategies=has_strategies,
        has_backtest_runs=has_runs,
        has_paper_accounts=has_paper,
    )
    if _lang() == "zh":
        loop_title = "让研究，触手可及。"
        loop_hint = "清晰的层级、灵活的输入与可解释的结果，让每个人都能顺畅进入量化研究。"
    else:
        loop_title = "Keep every insight within reach."
        loop_hint = "Clear hierarchy, flexible input and readable results make quantitative research easier for everyone to enter."
    st.markdown(
        f'''<div class="aq-research-loop-heading">
  <span class="aq-section-kicker">02 / RESEARCH LOOP</span>
  <h2>{loop_title}</h2>
  <p>{loop_hint}</p>
</div>''',
        unsafe_allow_html=True,
    )
    guide_copy = {
        "zh": {
            "data": ("清晰工作区", "用清楚的层级、对比度和留白，让重要信息一眼可见。", '<div class="aq-preview-top"><span>清晰工作区</span><b>AA</b></div><div class="aq-access-lines"><i class="wide"></i><i></i><i></i><i class="short"></i></div><div class="aq-preview-foot">清晰层级 · 舒适阅读</div>'),
            "universe": ("结构化导航", "通过大纲和分组快速定位研究内容，不迷失在复杂页面中。", '<div class="aq-preview-top"><span>研究大纲</span><b>03</b></div><div class="aq-preview-list"><span>01&nbsp; 研究问题</span><span>02&nbsp; 关键假设</span><span>03&nbsp; 风险检查</span></div>'),
            "strategy": ("灵活输入", "支持模板、可视化积木、自然语言与 Python，多种方式自由选择。", '<div class="aq-preview-inputs"><span>模板</span><span>积木</span><span>自然语言</span><span class="active">Python</span></div><div class="aq-preview-code"><span><em>ask</em>("解释这个因子")</span><span><strong>→</strong> readable answer</span></div>'),
            "backtest": ("专注分析", "聚焦当前指标和关键变化，减少噪声，让每一步判断更专注。", '<div class="aq-preview-focus"><span>年化收益</span><b>18.2%</b><span class="muted">其余指标已弱化</span></div><div class="aq-preview-line"></div>'),
            "review": ("可读结果", "把复杂的收益、回撤与风险信息转成容易理解的解释。", '<div class="aq-preview-report"><span><i></i>收益来源清晰</span><span><i></i>风险变化可追溯</span><span><i></i>结论附带解释</span></div><div class="aq-preview-foot">可解释报告</div>'),
            "paper": ("安全默认", "合理的默认值、明确的状态和逐步确认，降低误操作风险。", '<div class="aq-preview-safe"><span>下一步操作</span><b>模拟交易</b><em>已检查风险 · 可继续</em></div><div class="aq-preview-foot">明确状态 · 安全前进</div>'),
        },
        "en": {
            "data": ("Clear Workspace", "Clear hierarchy, contrast and whitespace keep important information easy to see.", '<div class="aq-preview-top"><span>CLEAR WORKSPACE</span><b>AA</b></div><div class="aq-access-lines"><i class="wide"></i><i></i><i></i><i class="short"></i></div><div class="aq-preview-foot">Clear hierarchy · easy reading</div>'),
            "universe": ("Structured Navigation", "Use outlines and groups to move through research without losing context.", '<div class="aq-preview-top"><span>RESEARCH OUTLINE</span><b>03</b></div><div class="aq-preview-list"><span>01&nbsp; Research question</span><span>02&nbsp; Key assumptions</span><span>03&nbsp; Risk checks</span></div>'),
            "strategy": ("Flexible Input", "Choose templates, visual blocks, natural language or Python for the task at hand.", '<div class="aq-preview-inputs"><span>Template</span><span>Blocks</span><span>Natural language</span><span class="active">Python</span></div><div class="aq-preview-code"><span><em>ask</em>("Explain this factor")</span><span><strong>→</strong> readable answer</span></div>'),
            "backtest": ("Focus Mode", "Keep attention on the active metric and meaningful changes, without visual noise.", '<div class="aq-preview-focus"><span>Annualized return</span><b>18.2%</b><span class="muted">Other metrics are softened</span></div><div class="aq-preview-line"></div>'),
            "review": ("Readable Results", "Turn complex return, drawdown and risk information into explanations people can follow.", '<div class="aq-preview-report"><span><i></i>Clear return sources</span><span><i></i>Traceable risk changes</span><span><i></i>Explained conclusions</span></div><div class="aq-preview-foot">EXPLAINABLE REPORT</div>'),
            "paper": ("Safe Defaults", "Sensible defaults, clear status and progressive confirmation reduce the risk of mistakes.", '<div class="aq-preview-safe"><span>Next action</span><b>Paper trading</b><em>Risk checked · ready</em></div><div class="aq-preview-foot">Clear status · safe progress</div>'),
        },
    }[_lang()]
    for row_start in range(0, len(steps), 3):
        columns = st.columns(3)
        for column, step in zip(columns, steps[row_start:row_start + 3], strict=True):
            with column:
                # key 供 CSS 做逐级延迟的滚动渐入，请勿改名（theme.py 有对应选择器）
                with st.container(border=True, key=f"aq_guide_step_{step.key}"):
                    card_title, card_hint, preview = guide_copy[step.key]
                    st.markdown(
                        f'<div class="aq-guide-preview aq-guide-preview-{step.key}">{preview}</div>'
                        f'<div class="aq-guide-card-title"><span>{card_title}</span></div>',
                        unsafe_allow_html=True,
                    )
                    st.caption(card_hint)


def _render_modules(report) -> None:
    """渲染模块直达卡片网格。"""
    render_section(_t("sec_modules"), _t("sec_modules_hint"))
    pool_ok = report.configured_symbols > 0
    footers = {
        "home.py": (
            ("ok" if report.ready_for_backtest else "warn"),
            _t("ready_footer") if report.ready_for_backtest else _t("not_ready_footer"),
        ),
        "pages/1_data_management.py": (
            _check_state(report, "股票行情"),
            _t("data_footer")
            .replace("{ok}", str(report.symbols_with_sufficient_history))
            .replace("{total}", str(report.configured_symbols)),
        ),
        "pages/5_universe_management.py": (
            "ok" if pool_ok else "err",
            _t("pool_footer_ok").replace("{n}", str(report.configured_symbols))
            if pool_ok
            else _t("pool_footer_empty"),
        ),
    }
    modules = _MODULES[_lang()]
    for offset in range(0, len(modules), 4):
        row = modules[offset : offset + 4]
        columns = st.columns(4)
        for column, (icon, title, desc, page, footer) in zip(
            columns, row, strict=False
        ):
            state, footer_text = footers.get(page, ("idle", footer))
            with column:
                render_module_card(
                    icon, title, desc, state, footer_text, delay_ms=offset * 60
                )
                if st.button(
                    _t("open"), key=f"welcome_module_{page}", use_container_width=True
                ):
                    strategy_modes = {
                        "pages/7_strategy_studio.py": "模板与积木",
                        "pages/8_custom_strategy.py": "Python 策略",
                        "pages/10_nl_strategy.py": "自然语言",
                    }
                    data_modes = {
                        "pages/1_data_management.py": "本地数据",
                        "pages/5_universe_management.py": "股票池",
                    }
                    if page in strategy_modes:
                        st.session_state["strategy_workspace_mode"] = strategy_modes[page]
                        st.switch_page("pages/0_strategy_hub.py")
                    elif page in data_modes:
                        st.session_state["data_assets_mode"] = data_modes[page]
                        st.switch_page("pages/13_data_assets.py")
                    elif page == "pages/2_research.py":
                        st.session_state["backtest_workspace_mode"] = (
                            "参数优化与稳健性验证"
                        )
                        st.switch_page("home.py")
                    elif page == "pages/3_risk_management.py":
                        st.session_state["paper_trading_mode"] = "风险规则"
                        st.switch_page("pages/4_paper_trading.py")
                    else:
                        st.switch_page(page)


def _render_status(report) -> None:
    """渲染平台状态：就绪度 + 环境检查行。"""
    render_section(_t("sec_status"), _t("sec_status_hint"))
    summary_col, rows_col = st.columns([1, 3], gap="large")
    with summary_col:
        pill_class = "aq-pill-ok" if report.ready_for_backtest else "aq-pill-warn"
        pill_text = _t("ready_pill") if report.ready_for_backtest else _t("warn_pill")
        st.markdown(
            f'<span class="aq-pill {pill_class}" style="height:32px;font-size:13px;">'
            f"{pill_text}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div style="margin-top:1rem;color:#81858c;font-size:0.85rem;'
            f'line-height:1.7;">{_t("status_note")}</div>',
            unsafe_allow_html=True,
        )
    with rows_col:
        for check in report.checks:
            render_check_row(
                check.item,
                _STATE_TO_DOT.get(check.status, "idle"),
                check.detail,
                check.destination or "",
            )


def _render_recent_runs(config_path: str) -> None:
    """渲染最近运行记录。"""
    render_section(_t("sec_runs"), _t("sec_runs_hint"))
    try:
        service = BacktestService(config_path)
        records = service.run_store.list_records()[:5]
        metadata = {item.plugin_name: item for item in service.available_strategies()}
        names = {name: item.display_name for name, item in metadata.items()}
    except Exception:
        records = []
        names = {}
    if not records:
        st.markdown(
            '<div style="color:#81858c;font-size:0.88rem;padding:0.4rem 0.2rem;">'
            f'{_t("no_runs")}</div>',
            unsafe_allow_html=True,
        )
        if st.button(_t("goto_backtest"), key="welcome_goto_backtest"):
            st.switch_page("home.py")
        return
    for record in records:
        label = format_run_label(record, names)
        meta = record.created_at[:16].replace("T", " ")
        render_run_row(
            label,
            _RUN_TO_DOT.get(record.status, "idle"),
            meta,
            RUN_KIND_LABELS.get(record.run_kind, record.run_kind),
        )
    if st.button(_t("all_runs"), key="welcome_all_runs"):
        st.switch_page("pages/6_run_library.py")


def _render_auth_modal(mode: str, logo_src: str) -> None:
    """渲染可提交到 SQLite 的注册/登录毛玻璃表单。"""
    store = AuthStore()
    is_login = mode == "login"
    if _lang() == "zh":
        tab_login, tab_register = "登录", "注册"
        title = "欢迎回来" if is_login else "创建你的账户"
        hint = "登录后继续你的量化研究。" if is_login else "建立一个属于你的研究工作台。"
        identity_label = "邮箱或用户名"
        username_label = "用户名"
        email_label = "邮箱"
        password_label = "密码"
        confirm_label = "再次确认密码"
        submit_label = "登录" if is_login else "注册"
        identity_placeholder = "you@example.com 或用户名"
        username_placeholder = "FellowQuant"
        email_placeholder = "you@example.com"
        password_placeholder = "至少 8 位密码"
        confirm_placeholder = "再次输入密码"
        note = "你的数据始终保存在本地工作台中。"
    else:
        tab_login, tab_register = "Log in", "Register"
        title = "Welcome back" if is_login else "Create your account"
        hint = "Sign in and continue your quantitative research." if is_login else "Set up a research workbench that belongs to you."
        identity_label = "Email or username"
        username_label = "Username"
        email_label = "Email"
        password_label = "Password"
        confirm_label = "Confirm password"
        submit_label = "Log in" if is_login else "Register"
        identity_placeholder = "you@example.com or username"
        username_placeholder = "FellowQuant"
        email_placeholder = "you@example.com"
        password_placeholder = "At least 8 characters"
        confirm_placeholder = "Enter password again"
        note = "Your data stays inside your local workbench."

    with st.container(key="aq_native_auth_modal"):
        with st.container(key="aq_native_auth_card"):
            header, close_col = st.columns([7, 1])
            with close_col:
                if st.button("×", key="aq_native_auth_close", help="Close"):
                    st.session_state.pop("aq_auth_mode", None)
                    st.rerun()
            with header:
                st.markdown(
                    f'<div class="aq-auth-brand"><img src="{logo_src}" alt="FellowQuant" /><span>FellowQuant</span></div>',
                    unsafe_allow_html=True,
                )
            tab_left, tab_right = st.columns(2)
            with tab_left:
                if st.button(
                    tab_login,
                    key="aq_native_auth_login_tab",
                    type="primary" if is_login else "secondary",
                    use_container_width=True,
                ):
                    st.session_state["aq_auth_mode"] = "login"
                    st.rerun()
            with tab_right:
                if st.button(
                    tab_register,
                    key="aq_native_auth_register_tab",
                    type="primary" if not is_login else "secondary",
                    use_container_width=True,
                ):
                    st.session_state["aq_auth_mode"] = "register"
                    st.rerun()
            st.markdown(f"<h3>{title}</h3><p>{hint}</p>", unsafe_allow_html=True)
            notice = st.session_state.pop("aq_auth_notice", "")
            if notice:
                st.success(notice)
            with st.form(key=f"aq_native_auth_form_{mode}", clear_on_submit=False):
                if is_login:
                    identity = st.text_input(identity_label, placeholder=identity_placeholder, key="aq_auth_identity")
                    password = st.text_input(password_label, placeholder=password_placeholder, type="password", key="aq_auth_login_password")
                    st.markdown('<div class="aq-auth-meta"><span class="aq-auth-link">Forgot password?</span></div>', unsafe_allow_html=True)
                    submitted = st.form_submit_button(submit_label, use_container_width=True)
                    if submitted:
                        result = store.authenticate(identity, password)
                        if result.ok:
                            st.session_state["aq_authenticated_user"] = result.username
                            st.session_state.pop("aq_auth_mode", None)
                            st.switch_page("home.py")
                        else:
                            st.error(result.message)
                else:
                    username = st.text_input(username_label, placeholder=username_placeholder, key="aq_auth_username")
                    email = st.text_input(email_label, placeholder=email_placeholder, key="aq_auth_email")
                    password = st.text_input(password_label, placeholder=password_placeholder, type="password", key="aq_auth_register_password")
                    confirmation = st.text_input(confirm_label, placeholder=confirm_placeholder, type="password", key="aq_auth_register_confirmation")
                    submitted = st.form_submit_button(submit_label, use_container_width=True)
                    if submitted:
                        result = store.register(username, email, password, confirmation)
                        if result.ok:
                            st.session_state["aq_auth_notice"] = result.message
                            st.session_state["aq_auth_mode"] = "login"
                            st.rerun()
                        else:
                            st.error(result.message)
            st.markdown(f'<p class="aq-auth-note">{note}</p>', unsafe_allow_html=True)


def _render_ending_page() -> None:
    """渲染主页结尾页；扩展功能区保留在代码中但默认不加载。"""
    logo_path = Path(__file__).parent / "assets" / "fellowquant-logo.png"
    logo_src = ""
    if logo_path.exists():
        logo_src = f"data:image/png;base64,{base64.b64encode(logo_path.read_bytes()).decode('ascii')}"
    authenticated_user = st.session_state.get("aq_authenticated_user")
    safe_username = escape(str(authenticated_user)) if authenticated_user else ""
    if _lang() == "zh":
        title = f"欢迎回来，{safe_username}" if authenticated_user else "want FellowQuant?"
        description = "身份已确认，继续你的量化研究" if authenticated_user else "一个简单的量化平台"
        subline = "AI-NATIVE RESEARCH WORKBENCH"
        register_label = "注册"
        login_label = "登录"
        workbench_label = "进入工作台"
        logout_label = "退出登录"
    else:
        title = f"Welcome back, {safe_username}" if authenticated_user else "want FellowQuant?"
        description = "Your session is active—continue your research" if authenticated_user else "A simple quantitative platform"
        subline = "AI-NATIVE RESEARCH WORKBENCH"
        register_label = "Register"
        login_label = "Log in"
        workbench_label = "Open workbench"
        logout_label = "Log out"
    if authenticated_user:
        ending_actions = f'''<button id="aq-enter-workbench" class="aq-ending-button aq-ending-button-login" type="button">{workbench_label}</button>
      <button id="aq-logout" class="aq-ending-button aq-ending-button-register" type="button">{logout_label}</button>'''
    else:
        ending_actions = f'''<button id="aq-open-register" class="aq-ending-button aq-ending-button-register" type="button">{register_label}</button>
      <button id="aq-open-login" class="aq-ending-button aq-ending-button-login" type="button">{login_label}</button>'''
    st.markdown(
        f'''<section class="aq-ending-page" aria-label="FellowQuant closing page">
  <div class="aq-ending-inner">
    <span class="aq-ending-kicker">FELLOWQUANT / ACCESSIBLE BY DESIGN</span>
    <h2 class="aq-ending-title">{title}</h2>
    <div class="aq-ending-offer">
      <img class="aq-ending-logo" src="{logo_src}" alt="FellowQuant icon" />
      <div class="aq-ending-description">{description}<small>{subline}</small></div>
    </div>
    <div class="aq-ending-actions">
      {ending_actions}
    </div>
  </div>
</section>''',
        unsafe_allow_html=True,
    )
    if _lang() == "zh":
        auth_login_title = "欢迎回来"
        auth_register_title = "创建你的账户"
        auth_login_hint = "登录后继续你的量化研究。"
        auth_register_hint = "建立一个属于你的研究工作台。"
        auth_username = "用户名"
        auth_email = "邮箱"
        auth_password = "密码"
        auth_confirm_password = "再次确认密码"
        auth_forgot = "忘记密码？"
        auth_login_submit = "登录"
        auth_register_submit = "注册"
        auth_note = "你的数据始终保存在本地工作台中。"
    else:
        auth_login_title = "Welcome back"
        auth_register_title = "Create your account"
        auth_login_hint = "Sign in and continue your quantitative research."
        auth_register_hint = "Set up a research workbench that belongs to you."
        auth_username = "Username"
        auth_email = "Email"
        auth_password = "Password"
        auth_confirm_password = "Confirm password"
        auth_forgot = "Forgot password?"
        auth_login_submit = "Log in"
        auth_register_submit = "Register"
        auth_note = "Your data stays inside your local workbench."
    st.markdown(
        f'''<div id="aq-auth-overlay" class="aq-auth-overlay" aria-hidden="true">
  <div class="aq-auth-backdrop" data-auth-close="true"></div>
  <section class="aq-auth-card" role="dialog" aria-modal="true" aria-label="Authentication">
    <button class="aq-auth-close" type="button" aria-label="Close" data-auth-close="true">×</button>
    <div class="aq-auth-brand"><img src="{logo_src}" alt="FellowQuant" /><span>FellowQuant</span></div>
    <div class="aq-auth-tabs">
      <button class="aq-auth-tab is-active" type="button" data-auth-mode="login">{login_label}</button>
      <button class="aq-auth-tab" type="button" data-auth-mode="register">{register_label}</button>
    </div>
    <div class="aq-auth-panel is-active" data-auth-panel="login">
      <h3>{auth_login_title}</h3><p>{auth_login_hint}</p>
      <label class="aq-auth-field">{auth_email} / {auth_username}<input type="text" placeholder="you@example.com or username" autocomplete="username" /></label>
      <label class="aq-auth-field">{auth_password}<input type="password" placeholder="••••••••" autocomplete="current-password" /></label>
      <div class="aq-auth-meta"><button class="aq-auth-link" type="button">{auth_forgot}</button></div>
      <button class="aq-auth-submit" type="button">{auth_login_submit}</button>
      <p class="aq-auth-note">{auth_note}</p>
    </div>
    <div class="aq-auth-panel" data-auth-panel="register">
      <h3>{auth_register_title}</h3><p>{auth_register_hint}</p>
      <label class="aq-auth-field">{auth_username}<input type="text" placeholder="FellowQuant" autocomplete="username" /></label>
      <label class="aq-auth-field">{auth_email}<input type="email" placeholder="you@example.com" autocomplete="email" /></label>
      <label class="aq-auth-field">{auth_password}<input type="password" placeholder="••••••••" autocomplete="new-password" /></label>
      <label class="aq-auth-field">{auth_confirm_password}<input type="password" placeholder="••••••••" autocomplete="new-password" /></label>
      <button class="aq-auth-submit" type="button">{auth_register_submit}</button>
      <p class="aq-auth-note">{auth_note}</p>
    </div>
  </section>
</div>''',
        unsafe_allow_html=True,
    )
    open_login = open_register = enter_workbench = logout = False
    with st.container(key="aq_auth_triggers"):
        if authenticated_user:
            enter_workbench = st.button("open workbench", key="aq_auth_open_workbench")
            logout = st.button("log out", key="aq_auth_logout")
        else:
            open_login = st.button("open login", key="aq_auth_open_login")
            open_register = st.button("open register", key="aq_auth_open_register")
    if enter_workbench:
        st.switch_page("home.py")
    if logout:
        _logout_authenticated_user()
        st.rerun()
    if open_login:
        st.session_state["aq_auth_mode"] = "login"
    elif open_register:
        st.session_state["aq_auth_mode"] = "register"
    if st.session_state.get("aq_auth_mode") in {"login", "register"}:
        _render_auth_modal(st.session_state["aq_auth_mode"], logo_src)
    bridge_script = (
        '''<script>
(() => {
  const doc = window.parent?.document || document;
  const trigger = (key) => doc.querySelector(`.st-key-${key} button`)?.click();
  doc.getElementById("aq-enter-workbench")?.addEventListener("click", () => trigger("aq_auth_open_workbench"));
  doc.getElementById("aq-logout")?.addEventListener("click", () => trigger("aq_auth_logout"));
})();
</script>'''
        if authenticated_user
        else '''<script>
(() => {
  const doc = window.parent?.document || document;
  const trigger = (key) => doc.querySelector(`.st-key-${key} button`)?.click();
  doc.getElementById("aq-open-login")?.addEventListener("click", () => trigger("aq_auth_open_login"));
  doc.getElementById("aq-open-register")?.addEventListener("click", () => trigger("aq_auth_open_register"));
})();
</script>'''
    )
    javascript_html(bridge_script)


_LOAD_EXTENDED_WELCOME_SECTIONS = False


def main() -> None:
    st.markdown(_OFFICIAL_HOME_CSS, unsafe_allow_html=True)
    st.markdown(_WELCOME_CRITICAL_CSS, unsafe_allow_html=True)
    config_path = "configs/app.yaml"  # 正式版固定配置路径，不再提供侧栏修改入口
    report = PlatformReadinessService(config_path).inspect()

    _render_particle_background()
    _render_launch_splash()
    _render_stickybar()
    _render_account_status()

    with st.container(key="aq_hero_wrap"):
        _render_hero(report)

    _render_product_overview()

    with st.container(key="aq_sec_guide"):
        _render_guide(report, config_path)
    _render_ending_page()

    # 这些页面暂时保留，后续需要时只需打开开关，不从项目中删除。
    if _LOAD_EXTENDED_WELCOME_SECTIONS:
        with st.container(key="aq_sec_modules"):
            _render_modules(report)
        with st.container(key="aq_sec_status"):
            _render_status(report)
        with st.container(key="aq_sec_runs"):
            _render_recent_runs(config_path)

        with st.container(key="aq_sec_detail"):
            st.divider()
            with st.expander(_t("trouble_title")):
                st.dataframe(report.to_frame(), width="stretch", hide_index=True)
                st.markdown(_t("trouble_body"))

    # 最后注入页面级覆盖，确保它位于主题与各组件自带 CSS 之后。
    st.markdown(_WELCOME_FINAL_CSS, unsafe_allow_html=True)


main()
