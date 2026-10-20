<script setup>
// 操作记录：管理员改了什么设置、停用了谁、启动了哪些数据任务、做过的备份。密钥本身不会出现在这里。
import { onMounted, ref } from 'vue'
import { adminAudit } from '../api.js'

const items = ref([])
const kinds = ref({})
const kind = ref('')
const limit = ref(100)
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const body = await adminAudit(kind.value, limit.value)
    items.value = body.items
    kinds.value = body.kinds
  } catch (e) { error.value = e.message || '加载失败' }
  finally { loading.value = false }
}
function choose(key) {
  kind.value = key
  limit.value = 100
  load()
}
function more() {
  limit.value += 100
  load()
}
onMounted(load)

const time = (iso) => new Date(iso).toLocaleString('zh-CN', { hour12: false })
</script>

<template>
  <section class="glass rounded-2xl p-5" aria-label="操作记录">
    <div class="flex flex-wrap items-center gap-3">
      <h2 class="text-sm font-semibold text-white">操作记录</h2>
      <div class="flex flex-wrap gap-2" role="group" aria-label="按种类筛选">
        <button v-for="[key, label] in [['', '全部'], ...Object.entries(kinds)]" :key="key" type="button" :aria-pressed="kind === key"
          class="rounded-full border px-3 py-1 text-xs transition"
          :class="kind === key ? 'border-indigo-400/50 bg-indigo-500/15 text-white' : 'border-white/10 text-slate-400 hover:text-slate-200'"
          @click="choose(key)">{{ label }}</button>
      </div>
      <button type="button" class="ml-auto text-xs text-indigo-300 hover:text-indigo-200 disabled:opacity-50" :disabled="loading" @click="load">刷新</button>
    </div>
    <p class="mt-2 text-xs text-slate-500">记录管理员做过的操作：改系统设置（只记改了哪些项，不记密钥）、停用或恢复用户、注册方式和邀请码、数据任务、备份。</p>
    <p v-if="error" role="alert" class="mt-4 text-sm text-rose-300">{{ error }}</p>
    <p v-else-if="loading && !items.length" class="mt-4 text-sm text-slate-400" role="status">正在读取…</p>
    <p v-else-if="!items.length" class="mt-4 text-sm text-slate-500">还没有记录。</p>
    <div v-else class="mt-4 overflow-x-auto">
      <table class="w-full min-w-[640px] text-left text-sm">
        <thead><tr class="text-xs text-slate-500"><th class="pb-2 pr-4 font-medium">时间</th><th class="pb-2 pr-4 font-medium">管理员</th><th class="pb-2 pr-4 font-medium">种类</th><th class="pb-2 font-medium">做了什么</th></tr></thead>
        <tbody class="divide-y divide-white/5">
          <tr v-for="row in items" :key="row.id" class="text-slate-300">
            <td class="whitespace-nowrap py-2 pr-4 text-xs text-slate-400">{{ time(row.created_at) }}</td>
            <td class="whitespace-nowrap py-2 pr-4 text-xs">{{ row.admin_email || '—' }}</td>
            <td class="whitespace-nowrap py-2 pr-4 text-xs text-slate-400">{{ row.kind }}</td>
            <td class="py-2">{{ row.summary }}</td>
          </tr>
        </tbody>
      </table>
      <button v-if="items.length >= limit && limit < 500" type="button" class="mt-3 text-xs text-indigo-300 hover:text-indigo-200" @click="more">再看 100 条</button>
    </div>
  </section>
</template>
