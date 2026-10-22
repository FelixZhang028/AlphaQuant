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
        <img src="/brand/prismind-icon-small.svg" width="27" height="27" alt="" aria-hidden="true" class="shrink-0" />
        <span class="ds-logo-wordmark">Prismind</span><span class="ds-logo-sub">镜思</span>
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
        <img src="/brand/prismind-icon-small.svg" width="27" height="27" alt="" aria-hidden="true" class="shrink-0" />
        <span class="ds-logo-wordmark">Prismind</span><span class="ds-logo-sub">镜思</span>
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
