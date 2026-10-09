<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import DynamicBackground from './DynamicBackground.vue'
import OnboardingTour from './OnboardingTour.vue'
import ThemeToggle from './ThemeToggle.vue'
import { allItems, groups, itemLabel, navigationItem, overviewKey, views } from '../workspace/modules.js'
import { getLocalUser, getToken, logout, me } from '../api.js'

const user = ref(getLocalUser())
const loading = ref(true)
const sidebarOpen = ref(false)
const activeKey = ref(initialViewKey())
const activeSection = computed(() => navigationItem(activeKey.value))
function isItemActive(item) { return activeSection.value?.key === item.key }
const toast = ref('')
const tourOpen = ref(false)
const githubUrl = 'https://github.com/FelixZhang028/AlphaQuant'

function navigate(key) {
  activeKey.value = key
  sidebarOpen.value = false
  const url = new URL(window.location.href)
  url.searchParams.set('view', key)
  window.history.pushState({}, '', url)
}
function syncView() { activeKey.value = initialViewKey() }
// 子视图可派发 `fq-navigate` 请求切换视图（如结果页深链审计页），与侧栏导航共用同一路径。
function onNavigateEvent(e) { navigate(e.detail) }
onMounted(() => {
  window.addEventListener('popstate', syncView)
  window.addEventListener('fq-navigate', onNavigateEvent)
})
onUnmounted(() => {
  window.removeEventListener('popstate', syncView)
  window.removeEventListener('fq-navigate', onNavigateEvent)
})

// 导航线性图标（Heroicons outline 路径），对齐 AlphaQuant 五组用户旅程
const navIcons = {
  overview:
    'M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75',
  'agent-lab':
    'M8.25 3v1.5M4.5 8.25H3m18 0h-1.5M4.5 12H3m18 0h-1.5m-15 3.75H3m18 0h-1.5M8.25 19.5V21M12 3v1.5m0 15V21m3.75-18v1.5m0 15V21m-9-1.5h10.5a2.25 2.25 0 002.25-2.25V6.75a2.25 2.25 0 00-2.25-2.25H6.75A2.25 2.25 0 004.5 6.75v10.5a2.25 2.25 0 002.25 2.25zm.75-12h9v9h-9v-9z',
  'nl-strategy':
    'M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 01-.825-.242m9.345-8.334a2.126 2.126 0 00-.476-.095 48.64 48.64 0 00-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0011.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155',
  'strategy-hub':
    'M12 18v-5.25m0 0a6.01 6.01 0 001.5-.189m-1.5.189a6.01 6.01 0 01-1.5-.189m3.75 7.478a12.06 12.06 0 01-4.5 0m3.75 2.383a14.406 14.406 0 01-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 10-7.517 0c.85.493 1.509 1.333 1.509 2.316V18',
  'strategy-studio':
    'M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z',
  'custom-strategy': 'M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5',
  'factor-lab':
    'M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714a2.25 2.25 0 00.659 1.591L19 14.5M14.25 3.104c.251.023.501.05.75.082M19 14.5l-1.34 5.089A2.25 2.25 0 0115.5 21h-7a2.25 2.25 0 01-2.16-1.411L5 14.5m14 0H5',
  'backtest-review':
    'M10.5 6h9.75M10.5 6a1.5 1.5 0 11-3 0m3 0a1.5 1.5 0 10-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-9.75 0h9.75',
  'audit-report':
    'M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25zM6.75 12h.008v.008H6.75V12zm0 3h.008v.008H6.75V15zm0 3h.008v.008H6.75V18z',
  'strategy-forensics':
    'M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607zM10.5 7.5v6m3-3h-6',
  research:
    'M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99',
  'run-library': 'M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z',
  'data-update':
    'M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3',
  'data-management':
    'M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 5.625c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125',
  'xtick-data': 'M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z',
  'risk-management':
    'M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z',
  universe:
    'M20.25 14.15v4.25c0 1.094-.787 2.036-1.872 2.18-2.087.277-4.216.42-6.378.42s-4.291-.143-6.378-.42c-1.085-.144-1.872-1.086-1.872-2.18v-4.25m16.5 0a2.18 2.18 0 00.75-1.661V8.706c0-1.081-.768-2.015-1.837-2.175a48.114 48.114 0 00-3.413-.387m4.5 8.006c-.194.165-.42.295-.673.38A23.978 23.978 0 0112 15.75c-2.648 0-5.195-.429-7.577-1.22a2.016 2.016 0 01-.673-.38m0 0A2.18 2.18 0 013 12.489V8.706c0-1.081.768-2.015 1.837-2.175a48.111 48.111 0 013.413-.387m7.5 0V5.25A2.25 2.25 0 0013.5 3h-3a2.25 2.25 0 00-2.25 2.25v.894m7.5 0a48.667 48.667 0 00-7.5 0M12 12.75h.008v.008H12v-.008z',
  account:
    'M17.982 18.725A7.488 7.488 0 0012 15.75a7.488 7.488 0 00-5.982 2.975m11.963 0a9 9 0 10-11.963 0m11.963 0A8.966 8.966 0 0112 21a8.966 8.966 0 01-5.982-2.275M15 9.75a3 3 0 11-6 0 3 3 0 016 0z',
  'decision-center':
    'M3.75 3v11.25A2.25 2.25 0 006 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0118 16.5h-2.25m-7.5 0h7.5m-7.5 0l-1 3m8.5-3l1 3m0 0l.5 1.5m-.5-1.5h-9.5m0 0l-.5 1.5m.75-9l3-3 2.148 2.148A12.061 12.061 0 0116.5 7.605',
  settings: 'M12 8.25a3.75 3.75 0 100 7.5 3.75 3.75 0 000-7.5M12 3v2m0 14v2M3 12h2m14 0h2M5.6 5.6 7 7m10 10 1.4 1.4M5.6 18.4 7 17m10-10 1.4-1.4',
  'prior-knowledge': 'M4 3h12a2 2 0 012 2v16H6a2 2 0 01-2-2V3zm4 5h6m-6 4h6m-6 4h4',
  'knowledge-base':
    'M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25',
}

// 初始视图：支持 /app.html?view=factor-lab 直达（落地页导航跳转用）
function initialViewKey() {
  const key = new URLSearchParams(window.location.search).get('view')
  return key && allItems.some((i) => i.key === key) ? key : overviewKey
}

function notify(msg) {
  toast.value = msg
  setTimeout(() => (toast.value = ''), 2600)
}

onMounted(async () => {
  if (!getToken()) {
    window.location.href = '/auth.html'
    return
  }
  try {
    user.value = await me()
  } catch {
    logout()
    window.location.href = '/auth.html'
    return
  }
  loading.value = false
  // 首次进入工作台自动弹出新手引导（可在顶栏 ? 图标重新打开）
  if (!localStorage.getItem('zt_tour_done')) tourOpen.value = true
})

function closeTour() {
  localStorage.setItem('zt_tour_done', '1')
  tourOpen.value = false
}

function doLogout() {
  logout()
  window.location.href = '/'
}
</script>

<template>
  <div class="relative min-h-screen text-slate-200">
    <DynamicBackground />

    <!-- 全局提示 -->
    <transition
      enter-active-class="transition duration-300"
      enter-from-class="opacity-0 translate-y-2"
      leave-active-class="transition duration-300"
      leave-to-class="opacity-0"
    >
      <div v-if="toast" class="fixed left-1/2 top-5 z-50 -translate-x-1/2 rounded-full border border-white/10 bg-ink/95 px-5 py-2.5 text-sm text-slate-200 shadow-xl">
        {{ toast }}
      </div>
    </transition>

    <div v-if="loading" class="flex min-h-screen items-center justify-center">
      <div class="h-8 w-8 animate-spin rounded-full border-2 border-white/20 border-t-indigo-400" />
    </div>

    <div v-else class="mx-auto flex max-w-[1500px]">
      <!-- 侧边栏 -->
      <aside
        :class="[
          'fixed inset-y-0 left-0 z-40 flex h-dvh w-72 shrink-0 flex-col transform border-r border-white/10 bg-ink/95 p-5 transition-transform duration-300 lg:sticky lg:top-0 lg:translate-x-0',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full',
        ]"
      >
        <a href="/" class="flex items-center gap-2.5">
          <img src="/fellowquant-logo.png" alt="FellowQuant" class="h-11 w-11 shrink-0 rounded-xl object-contain" />
          <div class="leading-tight">
            <p class="text-sm font-semibold text-white">FellowQuant</p>
            <p class="text-[10px] text-slate-500">功能台</p>
          </div>
        </a>

        <nav class="mt-5 min-h-0 flex-1 space-y-0.5 overflow-y-auto pr-1">
          <!-- 首页（顶层入口，对齐 AlphaQuant 用户旅程"我在哪"） -->
          <button
            @click="navigate(overviewKey)" :aria-current="activeKey === overviewKey ? 'page' : undefined"
            class="relative flex w-full items-start gap-2 rounded-lg px-3 py-2 text-sm transition whitespace-nowrap"
            :class="activeKey === overviewKey ? 'bg-white/5 text-fq-strong' : 'text-slate-400 hover:bg-white/5 hover:text-slate-200'"
          >
            <span v-if="activeKey === overviewKey" class="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r bg-blue-400" />
            <svg class="mt-0.5 h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6"><path stroke-linecap="round" stroke-linejoin="round" :d="navIcons.overview" /></svg>
            首页
          </button>

          <template v-for="group in groups" :key="group.label">
            <!-- 用户旅程分组：研究工作台 / 验证与审计 / 数据 / 系统 -->
            <p class="px-3 pb-1 pt-4 text-xs font-medium text-slate-500">{{ group.label }}</p>

            <button
              v-for="item in group.items"
              :key="item.key"
              @click="navigate(item.key)" :aria-current="isItemActive(item) ? 'page' : undefined"
              class="relative flex w-full items-start gap-2 rounded-lg py-2 pl-6 pr-2 text-sm transition whitespace-nowrap"
              :class="isItemActive(item) ? 'bg-white/5 text-fq-strong' : 'text-slate-400 hover:bg-white/5 hover:text-slate-200'"
            >
              <span v-if="isItemActive(item)" class="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r bg-blue-400" />
              <svg class="mt-0.5 h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6"><path stroke-linecap="round" stroke-linejoin="round" :d="navIcons[item.key] || ''" /></svg>
              {{ item.label }}
            </button>
          </template>
        </nav>

        <div class="mt-4 shrink-0 space-y-3 border-t border-white/10 pt-3">
          <section class="rounded-xl border border-white/10 bg-white/5 p-3" aria-label="支持 FellowQuant">
            <p class="text-sm font-semibold text-white">支持 FellowQuant</p>
            <p class="mt-2 text-[11px] leading-5 text-slate-400">您的<span class="text-indigo-300">意见</span>，都帮助我们持续改进。<br />您的<span class="text-amber-300">Star</span>，都是对我们最大的鼓励。</p>
            <div class="mt-3 flex gap-2">
              <a :href="`${githubUrl}/issues/new/choose`" target="_blank" rel="noopener noreferrer" class="flex-1 rounded-lg border border-white/10 px-2 py-2 text-center text-xs text-slate-300 hover:bg-white/10">提交 Issue</a>
              <a :href="githubUrl" target="_blank" rel="noopener noreferrer" class="flex-1 rounded-lg border border-white/10 px-2 py-2 text-center text-xs text-amber-300 hover:bg-white/10">☆ Star 项目</a>
            </div>
          </section>
          <button @click="navigate('account')" class="flex w-full items-center gap-3 rounded-xl p-2 text-left hover:bg-white/5" aria-label="打开个人中心">
            <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-indigo-500/20 font-semibold text-indigo-300">{{ (user?.name || 'U').slice(0, 1) }}</span>
            <span class="min-w-0"><span class="block truncate text-sm font-medium text-white">{{ user?.name }}</span><span class="mt-1 block text-xs text-emerald-400">● 已登录</span></span>
          </button>
        </div>
      </aside>

      <div class="min-w-0 flex-1">
        <header class="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-white/10 bg-ink/95 px-5 lg:px-8">
          <button class="rounded-lg p-2 text-slate-400 hover:bg-white/5 lg:hidden" @click="sidebarOpen = !sidebarOpen" aria-label="菜单">
            <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" d="M4 7h16M4 12h16M4 17h16" /></svg>
          </button>
          <h1 class="text-lg font-semibold text-white">{{ activeSection?.label || itemLabel(activeKey) }}</h1>
          <a href="/" class="hidden rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-xs text-slate-300 transition hover:border-white/25 hover:text-white sm:inline-flex">返回官网</a>

          <!-- 右上角：主题切换 + 新手引导 + 用户头像 + 名字 + 退出 -->
          <div class="ml-auto flex items-center gap-2">
            <ThemeToggle />
            <button
              class="flex h-8 w-8 items-center justify-center rounded-full border border-white/10 bg-white/5 text-sm text-slate-300 transition hover:border-indigo-400/40 hover:text-white"
              title="新手引导"
              aria-label="新手引导"
              @click="tourOpen = true"
            >
              <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3" /><circle cx="12" cy="17" r="0.8" fill="currentColor" stroke="none" /><circle cx="12" cy="12" r="10" stroke-width="2" /></svg>
            </button>
            <div class="flex items-center gap-2.5 rounded-full border border-white/10 bg-white/5 py-1 pl-1 pr-3">
              <span class="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-emerald-400 to-teal-500 text-xs font-bold text-ink">{{ (user?.name || 'U').slice(0, 1) }}</span>
              <span class="hidden max-w-[9rem] truncate text-sm font-medium text-white sm:inline">{{ user?.name }}</span>
            </div>
            <button
              class="flex h-8 w-8 items-center justify-center rounded-full border border-white/10 bg-white/5 text-slate-400 transition hover:border-rose-400/40 hover:bg-rose-400/10 hover:text-rose-300"
              title="退出登录"
              aria-label="退出登录"
              @click="doLogout"
            >
              <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M18.75 15L21.75 12m0 0l-3-3m3 3H9" /></svg>
            </button>
          </div>
        </header>

        <main class="space-y-6 p-5 lg:p-8">
          <nav v-if="activeSection?.children" :aria-label="`${activeSection.label}功能`" class="flex flex-wrap gap-2 rounded-xl border border-white/10 bg-white/5 p-2">
            <button v-for="tab in activeSection.children" :key="tab.key" @click="navigate(tab.key)"
              :aria-current="activeKey === tab.key ? 'page' : undefined"
              class="rounded-lg px-4 py-2 text-sm transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-400"
              :class="activeKey === tab.key ? 'bg-indigo-500/20 font-medium text-fq-strong' : 'text-slate-400 hover:bg-white/5 hover:text-slate-200'">
              {{ tab.label }}
            </button>
          </nav>
          <Suspense>
            <keep-alive :max="8">
              <component :is="views[activeKey] || views[overviewKey]" :user="user" :notify="notify" />
            </keep-alive>
            <template #fallback>
              <div class="flex items-center justify-center py-20">
                <div class="h-6 w-6 animate-spin rounded-full border-2 border-white/20 border-t-indigo-400" />
              </div>
            </template>
          </Suspense>
        </main>
      </div>
    </div>

    <div v-if="sidebarOpen && !loading" class="fixed inset-0 z-30 bg-black/50 backdrop-blur-sm lg:hidden" @click="sidebarOpen = false" />

    <OnboardingTour v-if="tourOpen && !loading" :user="user" @close="closeTour" />
  </div>
</template>
