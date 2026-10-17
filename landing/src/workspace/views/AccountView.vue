<script setup>
import { logout } from '../../api.js'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

function doLogout() {
  logout()
  window.location.href = '/'
}
</script>

<template>
  <div class="space-y-6">
    <section class="glass glass-sheen relative overflow-hidden rounded-2xl p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-indigo-500/20 blur-3xl" />
      <div class="flex items-center gap-4">
        <span class="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 text-2xl font-bold text-white shadow-lg shadow-indigo-500/40">{{ (user?.name || 'U').slice(0, 1) }}</span>
        <div>
          <p class="text-xl font-bold text-white">{{ user?.name }}</p>
          <p class="text-sm text-slate-400">{{ user?.email }}</p>
        </div>
      </div>
      <p class="mt-4 text-xs text-slate-500">注册时间：{{ user?.created_at || '—' }}</p>
    </section>

    <section class="glass rounded-2xl p-5">
      <h2 class="text-sm font-semibold text-white">账户信息</h2>
      <div class="mt-4 grid gap-4 sm:grid-cols-2">
        <div class="rounded-xl border border-white/10 bg-white/5 p-4">
          <p class="text-xs text-slate-400">用户编号</p>
          <p class="mt-1 font-mono text-sm text-indigo-300">U-{{ user?.id || '—' }}</p>
        </div>
        <div class="rounded-xl border border-white/10 bg-white/5 p-4">
          <p class="text-xs text-slate-400">账户类型</p>
          <p class="mt-1 text-sm text-white">{{ user?.is_admin ? '管理员' : '标准用户' }}</p>
        </div>
      </div>
    </section>

    <section class="glass rounded-2xl p-5">
      <h2 class="text-sm font-semibold text-white">会话</h2>
      <p class="mt-2 text-sm text-slate-400">退出登录后需要重新验证身份才能访问功能台。</p>
      <button @click="doLogout" class="mt-4 rounded-full border border-rose-400/20 px-5 py-2 text-sm text-rose-300 transition hover:bg-rose-400/10">退出登录</button>
    </section>
  </div>
</template>
