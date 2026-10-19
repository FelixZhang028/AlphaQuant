<script setup>
import { computed, ref } from 'vue'
import { setUserActive } from '../api.js'

// 用户列表：看每个人用了多少 AI、做了多少回测，可以停用或恢复账户。
const props = defineProps({ users: { type: Array, default: () => [] } })
const emit = defineEmits(['changed', 'notify'])

const keyword = ref('')
const order = ref('created')
const busy = ref(0)
const orders = [
  { value: 'created', label: '注册时间（新的在前）' },
  { value: 'ai_today', label: '今天的 AI 次数（多的在前）' },
  { value: 'ai_total', label: '累计 AI 次数（多的在前）' },
  { value: 'seen', label: '最后访问（近的在前）' },
]

const rows = computed(() => {
  const word = keyword.value.trim().toLowerCase()
  const list = props.users.filter((u) => !word || u.name.toLowerCase().includes(word) || u.email.toLowerCase().includes(word))
  const by = {
    created: (a, b) => b.id - a.id,
    ai_today: (a, b) => b.ai_today - a.ai_today || b.id - a.id,
    ai_total: (a, b) => b.ai_total - a.ai_total || b.id - a.id,
    seen: (a, b) => String(b.last_seen_at || '').localeCompare(String(a.last_seen_at || '')),
  }[order.value]
  return [...list].sort(by)
})

const time = (value) => (value ? new Date(value).toLocaleString() : '—')

async function toggle(user) {
  const next = !user.is_active
  const question = next
    ? `恢复「${user.name}」（${user.email}）？恢复后可以重新登录。`
    : `停用「${user.name}」（${user.email}）？停用后不能登录，已经登录的设备会立即退出。账户里的数据不会删除，以后可以恢复。`
  if (!window.confirm(question)) return
  busy.value = user.id
  try {
    await setUserActive(user.id, next)
    emit('notify', next ? `已恢复 ${user.name}` : `已停用 ${user.name}`)
    emit('changed')
  } catch (e) {
    emit('notify', e.message || '操作失败')
  } finally {
    busy.value = 0
  }
}
</script>

<template>
  <section class="glass rounded-2xl p-5" aria-label="用户">
    <div class="flex flex-wrap items-center gap-3">
      <h2 class="text-sm font-semibold text-white">注册用户</h2>
      <span class="text-xs text-slate-500">共 {{ users.length }} 人</span>
      <input v-model="keyword" placeholder="搜索用户名或邮箱" class="ml-auto w-56 rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-sm text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-400/40" />
      <select v-model="order" aria-label="排序" class="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-slate-200 outline-none">
        <option v-for="o in orders" :key="o.value" :value="o.value" class="bg-ink">{{ o.label }}</option>
      </select>
    </div>
    <p class="mt-2 text-xs text-slate-500">AI 次数包括 AI 解读、追问、生成规则、AI 评估和个股判断；某个人用得特别多时，可以先停用，查清楚再恢复。</p>
    <div class="mt-4 overflow-x-auto">
      <table class="[&_td]:whitespace-nowrap [&_th]:whitespace-nowrap [&_td]:px-3 [&_th]:px-3 [&_td:first-child]:pl-0 [&_th:first-child]:pl-0 [&_td:last-child]:pr-0 [&_th:last-child]:pr-0 w-full min-w-[900px] text-left text-sm">
        <thead>
          <tr class="text-xs text-slate-500">
            <th class="pb-3 font-medium">ID</th>
            <th class="pb-3 font-medium">用户</th>
            <th class="pb-3 font-medium">角色</th>
            <th class="pb-3 text-right font-medium">今天 AI</th>
            <th class="pb-3 text-right font-medium">累计 AI</th>
            <th class="pb-3 text-right font-medium">回测</th>
            <th class="pb-3 font-medium">注册时间</th>
            <th class="pb-3 font-medium">最后访问</th>
            <th class="pb-3 text-right font-medium">操作</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-white/5">
          <tr v-for="u in rows" :key="u.id" class="text-slate-300 transition hover:bg-white/5" :class="{ 'opacity-60': !u.is_active }">
            <td class="py-3 font-mono text-xs text-indigo-300">{{ u.id }}</td>
            <td class="py-3">
              <p class="font-medium text-white">{{ u.name }}</p>
              <p class="text-xs text-slate-500">{{ u.email }}</p>
            </td>
            <td class="py-3">
              <span v-if="u.is_admin" class="rounded-full border border-violet-400/30 bg-violet-400/10 px-2.5 py-0.5 text-xs text-violet-300">管理员</span>
              <span v-else-if="!u.is_active" class="rounded-full border border-rose-400/30 bg-rose-400/10 px-2.5 py-0.5 text-xs text-rose-300">已停用</span>
              <span v-else class="rounded-full border border-slate-400/20 bg-slate-400/10 px-2.5 py-0.5 text-xs text-slate-300">用户</span>
            </td>
            <td class="py-3 text-right font-medium" :class="u.ai_today ? 'text-white' : 'text-slate-500'">{{ u.ai_today }}</td>
            <td class="py-3 text-right text-slate-400">{{ u.ai_total }}</td>
            <td class="py-3 text-right text-slate-400">{{ u.backtests }}</td>
            <td class="py-3 text-slate-400">{{ time(u.created_at) }}</td>
            <td class="py-3 text-slate-400">{{ time(u.last_seen_at) }}</td>
            <td class="py-3 text-right">
              <button v-if="!u.is_admin" type="button" :disabled="busy === u.id"
                class="rounded-full border px-3 py-1 text-xs transition disabled:opacity-50"
                :class="u.is_active ? 'border-rose-400/30 text-rose-300 hover:bg-rose-400/10' : 'border-emerald-400/30 text-emerald-300 hover:bg-emerald-400/10'"
                @click="toggle(u)">{{ u.is_active ? '停用' : '恢复' }}</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="!rows.length" class="py-6 text-center text-sm text-slate-500">没有符合条件的用户。</p>
    </div>
  </section>
</template>
