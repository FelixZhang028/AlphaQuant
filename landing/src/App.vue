<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import QuantBackground from './components/QuantBackground.vue'
import { useScrollState } from './home/useScrollState'
import { CONTENT } from './home/homeContent'
import { useTheme } from './theme'
import { getToken } from './api.js'

const hasSession = ref(Boolean(getToken()))
const entryHref = computed(() => hasSession.value ? '/app.html' : '/auth.html')
const workspaceLabel = computed(() => lang.value === 'en' ? 'Open workspace' : '进入工作台')
function syncSession() { hasSession.value = Boolean(getToken()) }
onMounted(() => {
  syncSession()
  window.addEventListener('storage', syncSession)
  window.addEventListener('pageshow', syncSession)
  window.addEventListener('focus', syncSession)
})
onBeforeUnmount(() => {
  window.removeEventListener('storage', syncSession)
  window.removeEventListener('pageshow', syncSession)
  window.removeEventListener('focus', syncSession)
})

/* ---------- 原生滚动 / 滚动进度 / 鼠标视差 ---------- */
const { state: scrollState, update: updateScroll, scrollToSection } = useScrollState()

/* ---------- 主题（light / dark） ---------- */
const { theme, toggle: toggleTheme } = useTheme()

/* ---------- 语言（zh / en） ---------- */
const LANG_KEY = 'fq-lang'
const lang = ref(localStorage.getItem(LANG_KEY) === 'en' ? 'en' : 'zh')
const c = computed(() => CONTENT[lang.value])

function toggleLang() {
  lang.value = lang.value === 'zh' ? 'en' : 'zh'
  localStorage.setItem(LANG_KEY, lang.value)
  document.documentElement.lang = lang.value === 'zh' ? 'zh-CN' : 'en'
}
onMounted(() => {
  document.documentElement.lang = lang.value === 'zh' ? 'zh-CN' : 'en'
})

/* ---------- 导航 ---------- */
const navLinks = computed(() => [
  { id: 'home', label: c.value.nav.home },
  { id: 'belief', label: c.value.nav.belief },
  { id: 'features', label: c.value.nav.features },
  { id: 'about', label: c.value.nav.about },
])
// 服务体系区块归入「功能」导航项
const sectionNavMap = { home: 'home', belief: 'belief', services: 'features', features: 'features', about: 'about' }
const activeNav = ref('home')

const year = new Date().getFullYear()

/* ---------- 入场动画 / 导航激活态（rAF 主循环） ---------- */
let revealEls = []
let sectionEls = []
let rafId = 0

function checkReveals() {
  const trigger = window.innerHeight * 0.9
  for (const el of revealEls) {
    if (el.classList.contains('is-visible')) continue
    const rect = el.getBoundingClientRect()
    if (rect.top < trigger && rect.bottom > 0) el.classList.add('is-visible')
  }
}

function updateNav() {
  const mid = window.innerHeight * 0.5
  let activeId = 'home'
  for (const sec of sectionEls) {
    const rect = sec.getBoundingClientRect()
    if (rect.top <= mid && rect.bottom > mid) activeId = sec.id
  }
  activeNav.value = sectionNavMap[activeId] || activeId
}

function uiLoop() {
  rafId = requestAnimationFrame(uiLoop)
  updateScroll()
  checkReveals()
  updateNav()
}

function go(id) {
  scrollToSection(id)
}

onMounted(() => {
  revealEls = [...document.querySelectorAll('.fq-reveal')]
  sectionEls = ['home', 'belief', 'services', 'features', 'about']
    .map((id) => document.getElementById(id))
    .filter(Boolean)
  uiLoop()
})

onBeforeUnmount(() => cancelAnimationFrame(rafId))
</script>

<template>
  <div class="fq-site" :class="theme === 'light' ? 'fq-light' : 'fq-dark'">
    <!-- WebGL 失败时的 CSS 兜底背景 -->
    <div class="fq-fallback" aria-hidden="true"></div>

    <!-- Three.js 极光绸缎波场背景 + 暗角遮罩 -->
    <QuantBackground :scroll-state="scrollState" :theme="theme" />
    <div class="fq-voile" aria-hidden="true"></div>

    <!-- 顶栏：品牌 + 锚点导航 + 语言/主题/登录 -->
    <header class="fq-topbar">
      <a class="fq-logo" href="/index.html" aria-label="FellowQuant">
        <svg width="27" height="27" viewBox="0 0 27 27" fill="none" aria-hidden="true">
          <defs>
            <linearGradient id="fq-logo-grad" x1="0" y1="0" x2="27" y2="27" gradientUnits="userSpaceOnUse">
              <stop stop-color="#4d6bfe" />
              <stop offset="1" stop-color="#2e609f" />
            </linearGradient>
          </defs>
          <rect width="27" height="27" rx="8" fill="url(#fq-logo-grad)" />
          <path d="M7.4 17.6V11.4" stroke="#fff" stroke-width="1.7" stroke-linecap="round" />
          <rect x="5.9" y="12.4" width="3" height="3.7" rx="0.9" fill="#fff" />
          <path d="M13.5 15.2V7.9" stroke="#fff" stroke-width="1.7" stroke-linecap="round" />
          <rect x="12" y="9" width="3" height="4.5" rx="0.9" fill="#fff" />
          <path d="M19.6 12.7V5.6" stroke="#fff" stroke-width="1.7" stroke-linecap="round" />
          <rect x="18.1" y="6.8" width="3" height="4.9" rx="0.9" fill="#fff" />
        </svg>
        <span class="fq-logo-word">FellowQuant</span>
      </a>

      <nav class="fq-menu">
        <a
          v-for="link in navLinks"
          :key="link.id"
          :href="`#${link.id}`"
          class="fq-menu-link"
          :class="{ 'is-active': activeNav === link.id }"
          @click.prevent="go(link.id)"
        >
          {{ link.label }}
        </a>

        <div class="fq-actions">
          <button
            type="button"
            class="fq-icon-btn"
            :title="lang === 'zh' ? c.a11y.toEn : c.a11y.toZh"
            :aria-label="lang === 'zh' ? c.a11y.toEn : c.a11y.toZh"
            @click="toggleLang"
          >
            {{ lang === 'zh' ? 'EN' : '中' }}
          </button>
          <button
            type="button"
            class="fq-icon-btn"
            :title="theme === 'dark' ? c.a11y.toLight : c.a11y.toDark"
            :aria-label="theme === 'dark' ? c.a11y.toLight : c.a11y.toDark"
            @click="toggleTheme"
          >
            <!-- 深色显示太阳（点击进入浅色），浅色显示月亮 -->
            <svg v-if="theme === 'dark'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
            </svg>
            <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
            </svg>
          </button>
          <a :href="entryHref" class="fq-menu-login">{{ hasSession ? workspaceLabel : c.nav.login }}</a>
        </div>
      </nav>
    </header>

    <!-- 滚动内容（原生滚动） -->
    <main class="fq-content">
      <!-- HOME -->
      <section id="home" class="fq-section fq-hero">
        <div class="fq-hero-inner">
          <p class="fq-eyebrow fq-reveal" :style="{ transitionDelay: '0.15s' }">{{ c.hero.eyebrow }}</p>
          <h1 class="fq-hero-title">
            <span class="fq-reveal" :style="{ transitionDelay: '0.27s' }">Fellow</span><span
              class="fq-accent fq-reveal"
              :style="{ transitionDelay: '0.39s' }"
            >Quant</span>
          </h1>
          <p class="fq-hero-sub fq-reveal" :style="{ transitionDelay: '0.51s' }">{{ c.hero.sub }}</p>
          <p class="fq-hero-tag fq-reveal" :style="{ transitionDelay: '0.63s' }">
            {{ c.hero.tagLine1 }}<br />{{ c.hero.tagLine2 }}
          </p>
          <div class="fq-hero-cta fq-reveal" :style="{ transitionDelay: '0.75s' }">
            <a class="fq-btn fq-btn-solid" :href="entryHref">{{ hasSession ? workspaceLabel : c.hero.ctaPrimary }}</a>
            <a class="fq-btn" href="/app.html?view=nl-strategy">{{ c.hero.ctaSecondary }}</a>
          </div>
        </div>
        <div class="fq-scroll-hint fq-reveal" :style="{ transitionDelay: '0.9s' }">
          <span class="fq-dot"></span>
          <span>{{ c.hero.scrollHint }}</span>
        </div>
      </section>

      <!-- BELIEF -->
      <section id="belief" class="fq-section">
        <div class="fq-section-inner fq-narrow">
          <h2 class="fq-section-title"><span class="fq-index">01</span>{{ c.belief.title }}</h2>
          <h3 class="fq-headline fq-reveal" v-html="c.belief.headline"></h3>
          <p class="fq-text fq-reveal">{{ c.belief.p1 }}</p>
          <p class="fq-text fq-reveal">
            {{ c.belief.p2Prefix }}<span class="fq-gold">{{ c.belief.p2Gold }}</span>{{ c.belief.p2Suffix }}
          </p>
        </div>
      </section>

      <!-- SERVICES -->
      <section id="services" class="fq-section">
        <div class="fq-section-inner">
          <h2 class="fq-section-title"><span class="fq-index">02</span>{{ c.services.title }}</h2>
          <p class="fq-section-desc">{{ c.services.desc }}</p>
          <div class="fq-rows">
            <div
              v-for="(s, i) in c.services.items"
              :key="s.title"
              class="fq-row fq-reveal"
              :style="{ transitionDelay: `${(i % 5) * 0.07}s` }"
            >
              <div class="fq-row-num">{{ s.num }}</div>
              <div class="fq-row-content">
                <h3>{{ s.title }}</h3>
                <p class="fq-row-sub">{{ s.sub }}</p>
              </div>
              <div class="fq-row-progress"></div>
            </div>
          </div>
        </div>
      </section>

      <!-- FEATURES -->
      <section id="features" class="fq-section">
        <div class="fq-section-inner">
          <h2 class="fq-section-title"><span class="fq-index">03</span>{{ c.features.title }}</h2>
          <p class="fq-section-desc">{{ c.features.desc }}</p>
          <div class="fq-rows">
            <a
              v-for="(f, i) in c.features.items"
              :key="f.title"
              class="fq-row fq-row-link fq-reveal"
              :href="f.href"
              :style="{ transitionDelay: `${(i % 5) * 0.07}s` }"
            >
              <div class="fq-row-num">{{ f.num }}</div>
              <div class="fq-row-content">
                <h3>{{ f.title }}</h3>
                <p class="fq-row-sub">{{ f.sub }}</p>
              </div>
              <div class="fq-row-progress"></div>
            </a>
          </div>
        </div>
      </section>

      <!-- ABOUT -->
      <section id="about" class="fq-section">
        <div class="fq-section-inner fq-narrow">
          <h2 class="fq-section-title"><span class="fq-index">04</span>{{ c.about.title }}</h2>
          <h3 class="fq-headline fq-reveal" v-html="c.about.headline"></h3>
          <p class="fq-text fq-reveal">{{ c.about.p1 }}</p>
          <p class="fq-text fq-reveal">{{ c.about.p2 }}</p>
          <p class="fq-about-links fq-reveal">
            <a v-for="link in c.about.links" :key="link.href" :href="link.href === '/auth.html' ? entryHref : link.href">{{ link.label }} ↗</a>
          </p>
        </div>
      </section>

      <!-- FOOTER -->
      <footer class="fq-footer">
        <nav class="fq-footer-links">
          <a v-for="link in c.footer.links" :key="link.href" :href="link.href">{{ link.label }}</a>
        </nav>
        <p>{{ c.footer.disclaimer }}</p>
        <p class="fq-footer-meta">{{ c.footer.copyright(year) }}</p>
      </footer>
    </main>
  </div>
</template>

<style scoped>
/* ============ 设计令牌（dark 默认，light 覆盖见下） ============ */
.fq-site {
  --fq-bg: #000000;
  --fq-ink: #f4f7fc;
  --fq-ink-soft: rgba(244, 247, 252, 0.82);
  --fq-ink-dim: #8296b0;
  --fq-accent: #8fb0ff;
  --fq-gold: #e6c384;
  --fq-line: rgba(130, 150, 176, 0.16);
  --fq-accent-soft: rgba(143, 176, 255, 0.38);
  --fq-accent-strong: rgba(143, 176, 255, 0.9);
  --fq-accent-bg: rgba(77, 107, 254, 0.12);
  --fq-accent-glow: rgba(77, 107, 254, 0.32);
  --fq-ease: cubic-bezier(0.19, 1, 0.22, 1);
  --fq-font: 'Inter', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;

  position: relative;
  background: var(--fq-bg);
  color: var(--fq-ink);
  font-family: var(--fq-font);
  font-size: 16px;
  line-height: 1.6;
  overflow-x: hidden;
  transition: background 0.6s ease, color 0.6s ease;
  -webkit-font-smoothing: antialiased;
}

/* 浅色主题令牌覆盖（根元素 class 绑定，确保生效；文字用深蓝灰保证对比度） */
.fq-site.fq-light {
  --fq-bg: #eef4f6;
  --fq-ink: #16233a;
  --fq-ink-soft: rgba(22, 35, 58, 0.86);
  --fq-ink-dim: #475a73;
  --fq-accent: #2e609f;
  --fq-gold: #96702a;
  --fq-line: rgba(22, 35, 58, 0.14);
  --fq-accent-soft: rgba(46, 96, 159, 0.42);
  --fq-accent-strong: rgba(46, 96, 159, 0.88);
  --fq-accent-bg: rgba(46, 96, 159, 0.08);
  --fq-accent-glow: rgba(46, 96, 159, 0.18);
}

.fq-site :deep(*) {
  box-sizing: border-box;
}

.fq-site a {
  color: inherit;
}

/* ============ 兜底背景（WebGL 失败时） ============ */
.fq-fallback {
  position: fixed;
  inset: 0;
  z-index: 0;
  background:
    radial-gradient(90% 70% at 50% 100%, rgba(47, 157, 255, 0.12), transparent 70%),
    #000000;
}
.fq-site.fq-light .fq-fallback {
  background:
    radial-gradient(90% 70% at 50% 100%, rgba(73, 197, 182, 0.18), transparent 70%),
    linear-gradient(to bottom, #f7fafb, #eef4f6 55%, #e2edf0);
}

/* ============ 暗角遮罩 ============ */
.fq-voile {
  position: fixed;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  background:
    radial-gradient(120% 85% at 50% 38%, transparent 42%, rgba(0, 0, 0, 0.55) 100%),
    linear-gradient(to bottom, rgba(0, 0, 0, 0.35), transparent 18%, transparent 82%, rgba(0, 0, 0, 0.5));
}
.fq-site.fq-light .fq-voile {
  background:
    radial-gradient(120% 85% at 50% 38%, transparent 44%, rgba(226, 237, 240, 0.6) 100%),
    linear-gradient(to bottom, rgba(247, 250, 251, 0.55), transparent 18%, transparent 82%, rgba(233, 242, 245, 0.6));
}

/* ============ 内容层（原生滚动） ============ */
.fq-content {
  position: relative;
  z-index: 2;
}

/* ============ 顶栏 ============ */
.fq-topbar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 22px 40px;
}

.fq-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
}

.fq-logo-word {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.fq-menu {
  display: flex;
  align-items: center;
  gap: 26px;
}

.fq-menu-link {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.14em;
  text-decoration: none;
  opacity: 0.55;
  transition: opacity 0.5s ease;
}

.fq-menu-link:hover,
.fq-menu-link.is-active {
  opacity: 1;
}

.fq-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.fq-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  padding: 0;
  border: 1px solid var(--fq-accent-soft);
  border-radius: 50%;
  background: transparent;
  color: var(--fq-ink);
  font-size: 11px;
  font-weight: 700;
  font-family: var(--fq-font);
  letter-spacing: 0.02em;
  cursor: pointer;
  transition: border-color 0.5s ease, box-shadow 0.5s ease, background 0.5s ease, color 0.6s ease;
}

.fq-icon-btn:hover {
  border-color: var(--fq-accent-strong);
  background: var(--fq-accent-bg);
  box-shadow: 0 0 16px var(--fq-accent-glow);
}

.fq-menu-login {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.14em;
  text-decoration: none;
  padding: 8px 20px;
  border: 1px solid var(--fq-accent-soft);
  border-radius: 999px;
  transition: border-color 0.5s ease, box-shadow 0.5s ease, background 0.5s ease, color 0.6s ease;
}

.fq-menu-login:hover {
  border-color: var(--fq-accent-strong);
  background: var(--fq-accent-bg);
  box-shadow: 0 0 20px var(--fq-accent-glow);
}

/* ============ Section 通用 ============ */
.fq-section {
  position: relative;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 100px 0;
}

.fq-section-inner {
  width: min(760px, 88vw);
  margin: 0 auto;
}

.fq-narrow {
  width: min(640px, 88vw);
}

.fq-section-title {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.08em;
  margin-bottom: 14px;
}

.fq-index {
  font-size: 12px;
  font-weight: 600;
  color: var(--fq-gold);
}

.fq-section-desc {
  font-size: 14px;
  color: var(--fq-ink-dim);
  margin-bottom: 48px;
}

/* ============ Hero ============ */
.fq-hero {
  text-align: center;
}

.fq-hero-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 18px;
}

.fq-eyebrow {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.32em;
  text-transform: uppercase;
  color: var(--fq-ink-dim);
}

.fq-hero-title {
  font-size: clamp(56px, 10vw, 124px);
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.05;
  margin: 0;
}

.fq-accent {
  color: var(--fq-accent);
}

.fq-gold {
  color: var(--fq-gold);
}

.fq-hero-sub {
  font-size: clamp(16px, 2vw, 20px);
  font-weight: 600;
  letter-spacing: 0.24em;
  margin: 0;
}

.fq-hero-sub::before,
.fq-hero-sub::after {
  content: '·';
  color: var(--fq-gold);
  margin: 0 12px;
}

.fq-hero-tag {
  margin: 14px 0 0;
  max-width: min(680px, 86vw);
  font-size: 12px;
  line-height: 2;
  letter-spacing: 0.06em;
  color: var(--fq-ink-dim);
}

.fq-hero-cta {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 16px;
  margin-top: 26px;
}

.fq-btn {
  display: inline-flex;
  align-items: center;
  padding: 13px 32px;
  border: 1px solid var(--fq-accent-soft);
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-decoration: none;
  color: var(--fq-ink);
  transition: border-color 0.5s ease, box-shadow 0.5s ease, background 0.5s ease, transform 0.5s var(--fq-ease);
}

.fq-btn:hover {
  border-color: var(--fq-accent-strong);
  background: var(--fq-accent-bg);
  box-shadow: 0 0 28px var(--fq-accent-glow);
  transform: translateY(-2px);
}

.fq-btn-solid {
  background: linear-gradient(135deg, rgba(77, 107, 254, 0.92), rgba(46, 96, 159, 0.92));
  border-color: transparent;
  color: #fff;
}

.fq-btn-solid:hover {
  background: linear-gradient(135deg, #5d7bfe, #3a6db5);
  box-shadow: 0 8px 32px rgba(77, 107, 254, 0.45);
}

.fq-scroll-hint {
  position: absolute;
  bottom: 40px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 11px;
  letter-spacing: 0.28em;
  color: var(--fq-ink-dim);
}

.fq-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--fq-gold);
  animation: fq-pulse 2s infinite;
}

@keyframes fq-pulse {
  0% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.8); opacity: 0.4; }
  100% { transform: scale(1); opacity: 1; }
}

/* ============ 信念 / 关于 ============ */
.fq-headline {
  font-size: clamp(28px, 4vw, 40px);
  font-weight: 700;
  letter-spacing: -0.01em;
  line-height: 1.3;
  margin: 0 0 28px;
}

.fq-text {
  font-size: 15px;
  color: var(--fq-ink-soft);
  margin: 0 0 18px;
}

.fq-about-links {
  margin-top: 10px;
  font-size: 13px;
  display: flex;
  gap: 28px;
}

.fq-about-links a {
  color: var(--fq-ink);
  text-decoration: none;
  border-bottom: 1px solid var(--fq-line);
  padding-bottom: 1px;
  transition: color 0.3s ease, border-color 0.3s ease;
}

.fq-about-links a:hover {
  color: var(--fq-accent);
  border-color: var(--fq-accent);
}

/* ============ 功能 / 服务列表行 ============ */
.fq-rows {
  display: flex;
  flex-direction: column;
}

.fq-row {
  position: relative;
  display: flex;
  align-items: baseline;
  gap: 28px;
  padding: 22px 0;
  border-bottom: 1px solid var(--fq-line);
  overflow: hidden;
}

.fq-row-link {
  text-decoration: none;
  cursor: pointer;
}

.fq-row-num {
  flex: none;
  width: 30px;
  font-size: 12px;
  font-weight: 600;
  color: var(--fq-ink-dim);
  transition: color 0.4s ease;
}

.fq-row-content {
  display: flex;
  flex-direction: column;
  gap: 3px;
  transition: transform 0.6s var(--fq-ease);
}

.fq-row h3 {
  font-size: 30px;
  font-weight: 700;
  letter-spacing: -0.01em;
  line-height: 1.2;
  margin: 0;
  transition: color 0.4s ease;
}

.fq-row-sub {
  font-size: 14px;
  color: var(--fq-ink-dim);
  margin: 0;
  transition: color 0.4s ease;
}

.fq-row-progress {
  position: absolute;
  left: 0;
  bottom: -1px;
  height: 1px;
  width: 100%;
  background: linear-gradient(to right, var(--fq-accent), var(--fq-gold));
  transform: scaleX(0);
  transform-origin: left center;
  transition: transform 0.6s var(--fq-ease);
}

.fq-row:hover .fq-row-content {
  transform: translateX(28px);
}

.fq-row:hover .fq-row-sub {
  color: var(--fq-ink);
}

.fq-row:hover .fq-row-num {
  color: var(--fq-gold);
}

.fq-row:hover h3 {
  color: var(--fq-accent);
}

.fq-row:hover .fq-row-progress {
  transform: scaleX(1);
}

/* ============ Footer ============ */
.fq-footer {
  padding: 60px 0 44px;
  text-align: center;
}

.fq-footer-links {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 12px 28px;
  margin-bottom: 28px;
}

.fq-footer-links a {
  font-size: 12px;
  letter-spacing: 0.08em;
  color: var(--fq-ink-dim);
  text-decoration: none;
  transition: color 0.3s ease;
}

.fq-footer-links a:hover {
  color: var(--fq-accent);
}

.fq-footer p {
  font-size: 12px;
  color: var(--fq-ink-dim);
  letter-spacing: 0.06em;
  margin: 0;
}

.fq-footer-meta {
  margin-top: 8px;
  opacity: 0.6;
}

/* ============ 入场动画 ============ */
.fq-reveal {
  opacity: 0;
  transform: translateY(28px);
  transition: opacity 0.9s ease, transform 0.9s var(--fq-ease);
}

.fq-reveal.is-visible {
  opacity: 1;
  transform: translateY(0);
}

.fq-row.fq-reveal {
  transform: translateY(20px);
}

/* ============ 响应式 ============ */
@media (max-width: 768px) {
  .fq-topbar {
    padding: 18px 20px;
  }

  .fq-menu {
    gap: 16px;
  }

  .fq-menu-link {
    display: none;
  }

  .fq-logo-word {
    display: none;
  }

  .fq-menu-login {
    padding: 7px 16px;
  }

  .fq-row {
    gap: 16px;
    padding: 16px 0;
  }

  .fq-row h3 {
    font-size: 22px;
  }

  .fq-row:hover .fq-row-content {
    transform: translateX(14px);
  }

  .fq-section {
    padding: 80px 0;
  }

  .fq-section-desc {
    margin-bottom: 32px;
  }

  .fq-hero-tag {
    line-height: 1.9;
  }
}

@media (prefers-reduced-motion: reduce) {
  .fq-reveal {
    transition: none;
    opacity: 1;
    transform: none;
  }

  .fq-dot {
    animation: none;
  }
}
</style>
