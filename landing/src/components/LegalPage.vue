<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import FooterBar from './FooterBar.vue'
import DynamicBackground from './DynamicBackground.vue'
import LegalDocument from './LegalDocument.vue'
import ThemeToggle from './ThemeToggle.vue'
import { getLocalUser, getToken } from '../api.js'
import { backLink } from '../legal/legalBack.js'
import { documents, EFFECTIVE_DATE } from '../legal/legalContent.js'

// 顶栏和功能台一样：左边返回，右边主题切换和登录状态；不放首页的导航链接。
const back = backLink(document.referrer, window.location.origin)
const user = ref(null)
function syncSession() { user.value = getToken() ? (getLocalUser() || { name: '' }) : null }
const scrolled = ref(false)
function onScroll() { scrolled.value = window.scrollY > 4 }

// 一个页面放三份文件，用地址里的 #terms / #privacy / #risk 跳到对应的一份。
const active = ref('terms')
function sync() {
  const id = window.location.hash.slice(1)
  if (documents.some((doc) => doc.id === id)) active.value = id
}
onMounted(() => {
  sync()
  syncSession()
  onScroll()
  window.addEventListener('hashchange', sync)
  window.addEventListener('storage', syncSession)
  window.addEventListener('scroll', onScroll, { passive: true })
  if (window.location.hash) document.getElementById(active.value)?.scrollIntoView()
})
onBeforeUnmount(() => {
  window.removeEventListener('hashchange', sync)
  window.removeEventListener('storage', syncSession)
  window.removeEventListener('scroll', onScroll)
})
</script>

<template>
  <div class="min-h-screen text-slate-200">
    <DynamicBackground />
    <header class="sticky top-0 z-30 flex h-16 items-center gap-3 px-5 transition-colors duration-300 lg:px-8"
      :class="scrolled ? 'bg-ink/70 backdrop-blur-md' : 'bg-transparent'">
      <a class="flex shrink-0 items-center gap-2 no-underline" href="/index.html" aria-label="镜思 Prismind 首页">
        <img src="/brand/prismind-icon-small.svg" width="27" height="27" alt="" aria-hidden="true" class="shrink-0" />
        <span class="ds-logo-wordmark hidden sm:inline">Prismind</span><span class="ds-logo-sub hidden sm:inline">镜思</span>
      </a>
      <a :href="back.href" class="flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-xs text-slate-300 no-underline transition hover:border-white/25 hover:text-white">
        <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" /></svg>
        {{ back.label }}
      </a>

      <div class="ml-auto flex items-center gap-2">
        <ThemeToggle />
        <a v-if="user" href="/app.html" title="进入功能台"
          class="flex items-center gap-2.5 rounded-full border border-white/10 bg-white/5 py-1 pl-1 pr-3 no-underline transition hover:border-white/25">
          <span class="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-emerald-400 to-teal-500 text-xs font-bold text-ink">{{ (user.name || 'U').slice(0, 1) }}</span>
          <span class="max-w-[9rem] truncate text-sm font-medium text-white">{{ user.name || '进入功能台' }}</span>
        </a>
        <a v-else href="/auth.html" class="ds-btn-primary ds-btn-m no-underline">登录</a>
      </div>
    </header>

    <main class="mx-auto max-w-4xl px-5 pb-20 pt-6 lg:px-8">
      <div class="glass glass-sheen rounded-2xl p-8">
        <h1 class="text-2xl font-bold text-white sm:text-3xl">服务条款与政策</h1>
        <p class="mt-2 text-sm text-slate-400">生效日期：{{ EFFECTIVE_DATE }}</p>
        <nav class="mt-5 flex flex-wrap gap-2" aria-label="文件目录">
          <a
            v-for="doc in documents"
            :key="doc.id"
            :href="`#${doc.id}`"
            class="rounded-full border px-4 py-1.5 text-sm no-underline transition"
            :class="active === doc.id ? 'border-indigo-400/50 bg-indigo-500/15 text-white' : 'border-white/10 text-slate-300 hover:border-indigo-400/40'"
          >{{ doc.title }}</a>
        </nav>
      </div>

      <article v-for="doc in documents" :id="doc.id" :key="doc.id" class="glass mt-6 scroll-mt-20 rounded-2xl p-8">
        <h2 class="text-xl font-bold text-white">{{ doc.title }}</h2>
        <LegalDocument :doc="doc" class="mt-3" />
      </article>
    </main>

    <FooterBar />
  </div>
</template>
