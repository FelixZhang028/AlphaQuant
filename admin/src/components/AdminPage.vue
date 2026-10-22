<script setup>
import { computed, onMounted, ref } from 'vue'
import { SITE_BASE, adminAiUsage, adminStats, adminUsers, dailyUpdateStatus, systemStatus } from '../api.js'
import { bytes } from '../format.js'
import { barHeights, tokensText } from '../settings.js'
import AuditPanel from './AuditPanel.vue'
import DataPanel from './DataPanel.vue'
import InvitesPanel from './InvitesPanel.vue'
import SettingsPanel from './SettingsPanel.vue'
import UsersPanel from './UsersPanel.vue'

// 管理后台只显示平台的真实数字，并提供几项管理操作：停用账户、注册方式和邀请码、数据更新、
// 系统设置（AI 密钥、次数、数据更新、邮件服务）和操作记录。
const emit = defineEmits(['logout'])
const tabs = [
  { key: 'overview', label: '概览' },
  { key: 'users', label: '用户' },
  { key: 'invites', label: '注册与邀请码' },
  { key: 'data', label: '数据更新' },
  { key: 'settings', label: '系统设置' },
  { key: 'audit', label: '操作记录' },
]
const initial = window.location.hash.slice(1)
const tab = ref(tabs.some((t) => t.key === initial) ? initial : 'overview')
function openTab(key) {
  tab.value = key
  history.replaceState(null, '', `#${key}`)
  if (key === 'overview' || key === 'users') load()   // 切过来时拿最新的数字
}

const stats = ref(null)
const users = ref([])
const market = ref(null)
const system = ref(null)
const usage = ref(null)
const error = ref('')
const loading = ref(false)
const toast = ref('')
let toastTimer = null

function notify(message) {
  toast.value = message
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = '' }, 3500)
}

async function load() {
  loading.value = true
  error.value = ''
  const [s, u, m, sys, ai] = await Promise.allSettled([adminStats(), adminUsers(), dailyUpdateStatus(), systemStatus(), adminAiUsage(30)])
  if (s.status === 'fulfilled') stats.value = s.value
  else error.value = s.reason?.message || '统计加载失败'
  if (u.status === 'fulfilled') users.value = u.value
  if (m.status === 'fulfilled') market.value = m.value
  if (sys.status === 'fulfilled') system.value = sys.value
  if (ai.status === 'fulfilled') usage.value = ai.value
  loading.value = false
}
onMounted(load)

const number = (value) => (value == null ? '—' : Number(value).toLocaleString())

const cards = computed(() => {
  const s = stats.value
  if (!s) return []
  return [
    { label: '注册用户', value: number(s.users.total), sub: `今天新注册 ${number(s.users.new_today)} 人${s.users.disabled ? ` · 已停用 ${number(s.users.disabled)} 人` : ''}` },
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
const topUsers = computed(() => [...users.value].filter((u) => u.ai_today).sort((a, b) => b.ai_today - a.ai_today).slice(0, 5))

// 最近 30 天的 AI 用量：每天一根柱子，鼠标移上去看那天各类的次数。
const usageBars = computed(() => {
  const days = usage.value?.days || []
  const heights = barHeights(days)
  const labels = usage.value?.labels || {}
  return days.map((d, i) => ({
    day: d.day, height: heights[i], total: d.total,
    title: `${d.day}：共 ${d.total} 次${d.tokens ? `，token ${d.tokens}` : ''}` +
      Object.entries(d.kinds).filter(([, n]) => n).map(([k, n]) => `\n${labels[k] || k} ${n}`).join(''),
  }))
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
      <img src="/brand/prismind-icon-small.svg" alt="" aria-hidden="true" class="h-9 w-9 shrink-0 rounded-xl shadow-lg shadow-indigo-500/40" />
      <div class="leading-tight">
        <p class="text-sm font-semibold text-white">Prismind <span class="text-xs font-medium tracking-[0.3em] text-slate-400">镜思</span></p>
        <p class="text-xs text-slate-500">管理后台</p>
      </div>
      <div class="ml-auto flex items-center gap-2">
        <button type="button" :disabled="loading" class="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs text-slate-300 hover:text-white disabled:opacity-50" @click="load">{{ loading ? '刷新中…' : '刷新' }}</button>
        <a :href="`${SITE_BASE}/app.html`" class="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs text-slate-300 no-underline hover:text-white">打开功能台</a>
        <button type="button" class="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs text-slate-300 hover:text-white" @click="emit('logout')">退出</button>
      </div>
    </header>

    <nav class="mb-6 flex flex-wrap gap-2" aria-label="管理后台">
      <button v-for="t in tabs" :key="t.key" type="button" class="rounded-full border px-4 py-1.5 text-sm transition"
        :class="tab === t.key ? 'border-indigo-400/50 bg-indigo-500/15 text-white' : 'border-white/10 text-slate-400 hover:text-slate-200'"
        :aria-current="tab === t.key ? 'page' : undefined" @click="openTab(t.key)">{{ t.label }}</button>
    </nav>

    <p v-if="error" role="alert" class="mb-6 rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-200">{{ error }}</p>

    <main v-if="tab === 'overview'" class="space-y-6">
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
          <p class="mt-2 text-xs text-slate-500">全站每天的上限，用完以后当天所有用户暂停 AI 功能；管理员的调用也计入，但不受限制。上限和每人每天的次数可以在<button type="button" class="text-indigo-300 hover:text-indigo-200" @click="openTab('settings')">系统设置</button>里改。</p>
          <ul v-if="stats.ai.by_kind.length" class="mt-4 space-y-1.5 text-sm">
            <li v-for="k in stats.ai.by_kind" :key="k.kind" class="flex justify-between text-slate-300"><span>{{ k.label }}</span><span class="text-white">{{ number(k.count) }}</span></li>
          </ul>
          <p v-else class="mt-4 text-sm text-slate-500">今天还没有人用过 AI。</p>
          <div v-if="topUsers.length" class="mt-4 border-t border-white/10 pt-3">
            <p class="text-xs text-slate-400">今天用得最多的人</p>
            <ul class="mt-2 space-y-1.5 text-sm">
              <li v-for="u in topUsers" :key="u.id" class="flex justify-between text-slate-300"><span>{{ u.name }} <span class="text-xs text-slate-500">{{ u.email }}</span></span><span class="text-white">{{ u.ai_today }}</span></li>
            </ul>
            <button type="button" class="mt-3 text-xs text-indigo-300 hover:text-indigo-200" @click="openTab('users')">在“用户”里查看和停用 →</button>
          </div>
        </div>

        <div class="glass rounded-2xl p-5">
          <h2 class="text-sm font-semibold text-white">注册方式</h2>
          <p class="mt-3 text-lg font-semibold text-white">{{ modeText[stats.registration.mode] || stats.registration.mode }}</p>
          <p class="mt-1 text-xs text-slate-500">还能用的邀请码 {{ stats.registration.invites.filter((i) => i.limit == null || i.used < i.limit).length }} 个</p>
          <table v-if="stats.registration.invites.length" class="mt-4 w-full text-left text-sm">
            <thead><tr class="text-xs text-slate-500"><th class="pb-2 font-medium">邀请码</th><th class="pb-2 text-right font-medium">已用 / 可用</th></tr></thead>
            <tbody class="divide-y divide-white/5">
              <tr v-for="i in stats.registration.invites.slice(0, 6)" :key="i.code" class="text-slate-300">
                <td class="py-2 font-mono text-xs text-indigo-300">{{ i.code }}</td>
                <td class="py-2 text-right" :class="i.limit != null && i.used >= i.limit ? 'text-amber-300' : 'text-white'">{{ i.used }} / {{ i.limit ?? '不限' }}</td>
              </tr>
            </tbody>
          </table>
          <button type="button" class="mt-3 text-xs text-indigo-300 hover:text-indigo-200" @click="openTab('invites')">修改注册方式、生成邀请码 →</button>
        </div>
      </section>

      <section v-if="usage" class="glass rounded-2xl p-5" aria-label="最近 30 天的 AI 用量">
        <div class="flex flex-wrap items-baseline gap-3">
          <h2 class="text-sm font-semibold text-white">最近 30 天的 AI 用量</h2>
          <p class="text-xs text-slate-400">共 {{ number(usage.total) }} 次 · 文本模型 token {{ tokensText(usage.tokens) }}</p>
        </div>
        <div class="mt-4 flex h-28 items-end gap-1" role="img" :aria-label="`最近 30 天共 ${usage.total} 次`">
          <div v-for="bar in usageBars" :key="bar.day" class="flex h-full flex-1 items-end" :title="bar.title">
            <div class="w-full rounded-t bg-indigo-400/70" :class="bar.total ? '' : 'bg-white/10'" :style="{ height: `${Math.max(bar.height, bar.total ? 4 : 2)}%` }" />
          </div>
        </div>
        <div class="mt-1 flex justify-between text-[10px] text-slate-500"><span>{{ usageBars[0]?.day }}</span><span>{{ usageBars[usageBars.length - 1]?.day }}</span></div>
        <div class="mt-4 grid gap-5 md:grid-cols-2">
          <div>
            <p class="text-xs text-slate-400">各类 AI 功能</p>
            <ul class="mt-2 space-y-1.5 text-sm">
              <li v-for="(label, key) in usage.labels" :key="key" class="flex justify-between text-slate-300"><span>{{ label }}</span>
                <span class="text-white">{{ number(usage.days.reduce((sum, d) => sum + (d.kinds[key] || 0), 0)) }}</span></li>
            </ul>
          </div>
          <div>
            <p class="text-xs text-slate-400">30 天里用得最多的人</p>
            <ul v-if="usage.top_users.length" class="mt-2 space-y-1.5 text-sm">
              <li v-for="u in usage.top_users.slice(0, 6)" :key="u.id" class="flex justify-between gap-3 text-slate-300">
                <span class="min-w-0 truncate">{{ u.name }} <span class="text-xs text-slate-500">{{ u.email }}{{ u.is_admin ? ' · 管理员' : '' }}</span></span><span class="text-white">{{ number(u.count) }}</span></li>
            </ul>
            <p v-else class="mt-2 text-sm text-slate-500">还没有人用过 AI。</p>
          </div>
        </div>
        <p class="mt-3 text-[11px] text-slate-500">token 只在服务商返回了用量时才有记录（决策模型 Jev 不返回），可以用来估算费用。</p>
      </section>

      <section class="glass rounded-2xl p-5" aria-label="数据与备份">
        <h2 class="text-sm font-semibold text-white">数据与备份</h2>
        <p v-if="system?.disk?.warning" role="alert" class="mt-3 rounded-xl border border-rose-400/30 bg-rose-500/10 px-4 py-2.5 text-sm text-rose-200">磁盘只剩 {{ bytes(system.disk.free) }}，空间不够时每日更新和备份会失败。</p>
        <dl class="mt-4 grid gap-4 text-sm sm:grid-cols-4">
          <div><dt class="text-xs text-slate-400">行情数据</dt><dd class="mt-1 text-slate-200">{{ marketText }}</dd></div>
          <div><dt class="text-xs text-slate-400">每天自动更新</dt><dd class="mt-1 text-slate-200">{{ market?.text || '—' }}</dd></div>
          <div><dt class="text-xs text-slate-400">账户数据备份</dt><dd class="mt-1 text-slate-200">{{ backupText }}</dd></div>
          <div><dt class="text-xs text-slate-400">磁盘剩余</dt><dd class="mt-1" :class="system?.disk?.warning ? 'text-rose-300' : 'text-slate-200'">{{ system ? `${bytes(system.disk.free)} / ${bytes(system.disk.total)}` : '—' }}</dd></div>
        </dl>
        <button type="button" class="mt-3 text-xs text-indigo-300 hover:text-indigo-200" @click="openTab('data')">查看每一步结果、财务数据、下载历史数据、备份 →</button>
      </section>
    </main>

    <UsersPanel v-else-if="tab === 'users'" :users="users" @changed="load" @notify="notify" />
    <InvitesPanel v-else-if="tab === 'invites'" @changed="load" @notify="notify" />
    <DataPanel v-else-if="tab === 'data'" :site-base="SITE_BASE" @notify="notify" />
    <SettingsPanel v-else-if="tab === 'settings'" @notify="notify" />
    <AuditPanel v-else-if="tab === 'audit'" />

    <transition enter-active-class="transition duration-200" enter-from-class="opacity-0 translate-y-2" leave-active-class="transition duration-200" leave-to-class="opacity-0">
      <p v-if="toast" role="status" class="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-full border border-white/15 bg-ink/90 px-5 py-2.5 text-sm text-white shadow-lg">{{ toast }}</p>
    </transition>
  </div>
</template>
