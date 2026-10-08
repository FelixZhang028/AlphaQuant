<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import ThemeToggle from './ThemeToggle.vue'

// 滚动玻璃态：scrollY > 80 时加 is-scrolled
const scrolled = ref(false)
const menuOpen = ref(false)

const links = [
  { label: '策略中心', href: '/app.html?view=strategy-hub' },
  { label: '回测系统', href: '/app.html?view=backtest-review' },
  { label: '因子实验室', href: '/app.html?view=factor-lab' },
  { label: '社区论坛', href: '/community.html' },
]

function onScroll() {
  scrolled.value = window.scrollY > 80
}

// 打开移动菜单时锁定页面滚动
function lockScroll(open) {
  document.body.style.overflow = open ? 'hidden' : ''
}

// ESC 关闭移动菜单
function onKeydown(e) {
  if (e.key === 'Escape') closeMenu()
}

function openMenu() {
  menuOpen.value = true
  lockScroll(true)
}
function closeMenu() {
  menuOpen.value = false
  lockScroll(false)
}

onMounted(() => {
  onScroll()
  window.addEventListener('scroll', onScroll, { passive: true })
  document.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScroll)
  document.removeEventListener('keydown', onKeydown)
  lockScroll(false)
})
</script>

<template>
  <div class="ds-header-wrapper">
    <div class="ds-header-bar" :class="{ 'is-scrolled': scrolled }">
      <!-- 左：Logo -->
      <a class="flex shrink-0 items-center gap-2 no-underline" href="/index.html">
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
        <span class="ds-logo-wordmark">FellowQuant</span>
      </a>

      <!-- 中：导航链接（≥768px） -->
      <div class="hidden items-center gap-ds-2 md:flex">
        <a v-for="link in links" :key="link.label" :href="link.href" class="ds-btn-ghost ds-btn-nav no-underline">
          {{ link.label }}
        </a>
      </div>

      <!-- 右：主题切换 + 登录 + 移动端汉堡 -->
      <div class="flex items-center gap-ds-2">
        <ThemeToggle />
        <a href="/auth.html" class="ds-btn-primary ds-btn-m no-underline">登录</a>
        <button
          type="button"
          class="flex h-10 w-10 items-center justify-center text-ds-primary md:hidden"
          aria-label="打开菜单"
          @click="openMenu"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M3 6h18M3 12h18M3 18h18" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
          </svg>
        </button>
      </div>
    </div>
  </div>

  <!-- 移动端全屏菜单 -->
  <div class="ds-mobile-menu" :class="{ 'is-open': menuOpen }">
    <div class="ds-mobile-menu-header">
      <a class="flex items-center gap-2 no-underline" href="/index.html" @click="closeMenu">
        <svg width="27" height="27" viewBox="0 0 27 27" fill="none" aria-hidden="true">
          <rect width="27" height="27" rx="8" fill="url(#fq-logo-grad)" />
          <path d="M7.4 17.6V11.4" stroke="#fff" stroke-width="1.7" stroke-linecap="round" />
          <rect x="5.9" y="12.4" width="3" height="3.7" rx="0.9" fill="#fff" />
          <path d="M13.5 15.2V7.9" stroke="#fff" stroke-width="1.7" stroke-linecap="round" />
          <rect x="12" y="9" width="3" height="4.5" rx="0.9" fill="#fff" />
          <path d="M19.6 12.7V5.6" stroke="#fff" stroke-width="1.7" stroke-linecap="round" />
          <rect x="18.1" y="6.8" width="3" height="4.9" rx="0.9" fill="#fff" />
        </svg>
        <span class="ds-logo-wordmark">FellowQuant</span>
      </a>
      <button
        type="button"
        class="flex h-10 w-10 items-center justify-center text-ds-primary"
        aria-label="关闭菜单"
        @click="closeMenu"
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
          <path d="M6 6l12 12M6 18L18 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
        </svg>
      </button>
    </div>
    <nav class="ds-mobile-menu-body">
      <a v-for="link in links" :key="link.label" :href="link.href" class="ds-mobile-menu-item" @click="closeMenu">
        {{ link.label }}
      </a>
      <a href="/auth.html" class="ds-mobile-menu-item" @click="closeMenu">登录 / 注册</a>
    </nav>
  </div>
</template>
