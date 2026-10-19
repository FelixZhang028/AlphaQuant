<script setup>
import { computed, onMounted, ref } from 'vue'
import { adminStats, adminUsers, dailyUpdateStatus } from '../api.js'

// 管理后台只显示平台的真实数字：用户、研究、AI 用量、注册方式、行情数据和备份。
const emit = defineEmits(['logout'])
const stats = ref(null)
const users = ref([])
const market = ref(null)
const error = ref('')
const loading = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  const [s, u, m] = await Promise.allSettled([adminStats(), adminUsers(), dailyUpdateStatus()])
  if (s.status === 'fulfilled') stats.value = s.value
  else error.value = s.reason?.message || '统计加载失败'
  if (u.status === 'fulfilled') users.value = u.value
  if (m.status === 'fulfilled') market.value = m.value
  loading.value = false
}
onMounted(load)

const number = (value) => (value == null ? '—' : Number(value).toLocaleString())
const time = (value) => (value ? new Date(value).toLocaleString() : '—')

const cards = computed(() => {
  const s = stats.value
  if (!s) return []
  return [
    { label: '注册用户', value: number(s.users.total), sub: `今天新注册 ${number(s.users.new_today)} 人` },
    { label: '今天活跃', value: number(s.users.active_today), sub: '今天打开过功能台的用户' },
    { label: '回测记录', value: number(s.research.backtests), sub: `今天 ${number(s.research.backtests_today)} 次 · 保存的策略 ${number(s.research.strategies)} 个` },
    { label: 'AI 研究员分析', value: number(s.research.briefs), sub: `今天 ${number(s.research.briefs_today)} 次` },
  ]
})

const aiShare = computed(() => {
  const ai = stats.value?.ai
  if (!ai?.limit) return null
  return Math.min(100, Math.round((ai.used / ai.limit) * 100))
})

const modeText = { open: '开放注册', invite: '凭邀请码注册', closed: '暂停注册' }
const backupText = computed(() => {
  const b = stats.value?.backup
  if (!b) return '—'
  if (!b.enabled) return '自动备份已关闭'
  return b.latest ? `最近一次 ${b.latest}，共 ${b.count} 份（保留 ${b.keep} 份）` : '还没有备份'
})
const marketText = computed(() => {
  const d = market.value?.data
  if (!d) return '—'
  return d.latest_date ? `${d.latest_date}，${number(d.stocks_on_latest)} / ${number(d.listed)} 只股票已更新到这一天` : '还没有行情数据'
})
</script>

<template>
  <div class="mx-auto max-w-6xl px-5 pb-16 lg:px-8">
    <header class="flex flex-wrap items-center gap-3 py-6">
      <span class="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-base font-bold text-white shadow-lg shadow-indigo-500/40">F</span>
      <div class="leading-tight">
        <p class="text-sm font-semibold text-white">FellowQuant</p>
        <p class="text-xs text-slate-500">管理后台</p>
      </div>
      <div class="ml-auto flex items-center gap-2">
        <button type="button" :disabled="loading" class="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs text-slate-300 hover:text-white disabled:opacity-50" @click="load">{{ loading ? '刷新中…' : '刷新' }}</button>
        <a href="/app.html" class="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs text-slate-300 no-underline hover:text-white">打开功能台</a>
        <button type="button" class="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs text-slate-300 hover:text-white" @click="emit('logout')">退出</button>
      </div>
    </header>

    <main class="space-y-6">
      <p v-if="error" role="alert" class="rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-200">{{ error }}</p>

      <section class="grid gap-5 sm:grid-cols-2 xl:grid-cols-4" aria-label="概况">
        <div v-for="c in cards" :key="c.label" class="glass glass-sheen rounded-2xl p-5">
          <p class="text-xs text-slate-400">{{ c.label }}</p>
          <p class="mt-2 text-3xl font-bold text-white">{{ c.value }}</p>
          <p class="mt-2 text-xs text-slate-500">{{ c.sub }}</p>
        </div>
      </section>

      <section v-if="stats" class="grid gap-5 lg:grid-cols-2">
        <div class="glass rounded-2xl p-5">
          <h2 class="text-sm font-semibold text-white">今天的 AI 用量</h2>
          <p class="mt-3 text-2xl font-bold text-white">{{ number(stats.ai.used) }} <span class="text-sm font-normal text-slate-400">/ {{ stats.ai.limit ? number(stats.ai.limit) : '不限' }} 次</span></p>
          <div v-if="aiShare != null" class="mt-3 h-2 overflow-hidden rounded-full bg-white/10" aria-hidden="true">
            <div class="h-full rounded-full" :class="aiShare >= 90 ? 'bg-rose-400' : aiShare >= 70 ? 'bg-amber-400' : 'bg-indigo-400'" :style="{ width: `${aiShare}%` }" />
          </div>
          <p class="mt-2 text-xs text-slate-500">全站每天的上限（FELLOWQUANT_AI_DAILY_TOTAL），用完以后当天所有用户暂停 AI 功能；管理员的调用也计入，但不受限制。</p>
          <ul v-if="stats.ai.by_kind.length" class="mt-4 space-y-1.5 text-sm">
            <li v-for="k in stats.ai.by_kind" :key="k.kind" class="flex justify-between text-slate-300"><span>{{ k.label }}</span><span class="text-white">{{ number(k.count) }}</span></li>
          </ul>
          <p v-else class="mt-4 text-sm text-slate-500">今天还没有人用过 AI。</p>
        </div>

        <div class="glass rounded-2xl p-5">
          <h2 class="text-sm font-semibold text-white">注册方式</h2>
          <p class="mt-3 text-lg font-semibold text-white">{{ modeText[stats.registration.mode] || stats.registration.mode }}</p>
          <p class="mt-1 text-xs text-slate-500">在服务器的 .env 里设置（FELLOWQUANT_INVITE_CODES、FELLOWQUANT_REGISTRATION），改完重启后端。</p>
          <table v-if="stats.registration.invites.length" class="mt-4 w-full text-left text-sm">
            <thead><tr class="text-xs text-slate-500"><th class="pb-2 font-medium">邀请码</th><th class="pb-2 text-right font-medium">已用 / 可用</th></tr></thead>
            <tbody class="divide-y divide-white/5">
              <tr v-for="i in stats.registration.invites" :key="i.code" class="text-slate-300">
                <td class="py-2 font-mono text-xs text-indigo-300">{{ i.code }}</td>
                <td class="py-2 text-right" :class="i.limit != null && i.used >= i.limit ? 'text-amber-300' : 'text-white'">{{ i.used }} / {{ i.limit ?? '不限' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="glass rounded-2xl p-5" aria-label="数据与备份">
        <h2 class="text-sm font-semibold text-white">数据与备份</h2>
        <dl class="mt-4 grid gap-4 text-sm sm:grid-cols-3">
          <div><dt class="text-xs text-slate-400">行情数据</dt><dd class="mt-1 text-slate-200">{{ marketText }}</dd></div>
          <div><dt class="text-xs text-slate-400">每天自动更新</dt><dd class="mt-1 text-slate-200">{{ market?.text || '—' }}</dd></div>
          <div><dt class="text-xs text-slate-400">账户数据备份</dt><dd class="mt-1 text-slate-200">{{ backupText }}</dd></div>
        </dl>
      </section>

      <section class="glass rounded-2xl p-5" aria-label="注册用户">
        <div class="flex items-center justify-between">
          <h2 class="text-sm font-semibold text-white">注册用户</h2>
          <span class="text-xs text-slate-500">共 {{ users.length }} 人</span>
        </div>
        <div class="mt-4 overflow-x-auto">
          <table class="w-full min-w-[640px] text-left text-sm">
            <thead>
              <tr class="text-xs text-slate-500">
                <th class="pb-3 font-medium">ID</th>
                <th class="pb-3 font-medium">用户名</th>
                <th class="pb-3 font-medium">邮箱</th>
                <th class="pb-3 font-medium">角色</th>
                <th class="pb-3 font-medium">注册时间</th>
                <th class="pb-3 font-medium">最后访问</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-white/5">
              <tr v-for="u in users" :key="u.id" class="text-slate-300 transition hover:bg-white/5">
                <td class="py-3 font-mono text-xs text-indigo-300">{{ u.id }}</td>
                <td class="py-3 font-medium text-white">{{ u.name }}</td>
                <td class="py-3 text-slate-400">{{ u.email }}</td>
                <td class="py-3">
                  <span class="rounded-full border px-2.5 py-0.5 text-xs" :class="u.is_admin ? 'border-violet-400/30 bg-violet-400/10 text-violet-300' : 'border-slate-400/20 bg-slate-400/10 text-slate-300'">{{ u.is_admin ? '管理员' : '用户' }}</span>
                </td>
                <td class="py-3 text-slate-400">{{ time(u.created_at) }}</td>
                <td class="py-3 text-slate-400">{{ time(u.last_seen_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </main>
  </div>
</template>
