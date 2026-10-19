<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { dailyUpdateStatus, dataJobs, runDailyUpdate, stopDataJob } from '../api.js'

// 数据更新：看每天自动更新的情况和后台任务的进度，可以马上运行今天的更新或停止正在运行的任务。
// 下载一段历史、更新单只股票等更细的操作在功能台的“数据更新”页。
defineProps({ siteBase: { type: String, default: '' } })
const emit = defineEmits(['notify'])
const daily = ref(null)
const jobs = ref([])
const error = ref('')
const starting = ref(false)
let timer = null

const DATASETS = {
  daily: '每日更新', bars: '日线行情', actions: '分红送配', derived: '历史股票池等衍生数据', indicators: '估值与换手率',
  fundamentals: '财务数据', industry: '行业分类', index_constituents: '指数成分股', bar_gaps: '补全行情', action_gaps: '补全分红送转记录',
}
const STAGES = {
  daily_indicators: '估值与换手率', quarterly_fundamentals: '财务数据', industry: '行业分类', index_constituents: '指数成分股',
  bar_gaps: '补全行情', corporate_action_gaps: '补全分红送转记录', security_master: '证券主表', daily_bars: '日线行情',
  corporate_actions: '分红送配', universe_membership: '历史股票池',
}
const ACTIVE = new Set(['STARTING', 'RUNNING', 'RETRYING'])

async function load() {
  error.value = ''
  const [d, j] = await Promise.allSettled([dailyUpdateStatus(), dataJobs()])
  if (d.status === 'fulfilled') daily.value = d.value
  else error.value = d.reason?.message || '加载失败'
  if (j.status === 'fulfilled') jobs.value = j.value.records || []
  schedule()
}

const running = computed(() => jobs.value.find((job) => ACTIVE.has(job.status)) || null)
const recent = computed(() => jobs.value.slice(0, 8))

// 有任务在跑时每 5 秒刷新一次进度。
function schedule() {
  clearTimeout(timer)
  if (running.value) timer = setTimeout(load, 5000)
}
onMounted(load)
onBeforeUnmount(() => clearTimeout(timer))

function percent(progress) {
  if (!progress?.total) return 0
  return Math.min(100, Math.round((progress.done / progress.total) * 100))
}
const datasetText = (job) => (job.datasets || []).map((d) => DATASETS[d] || d).join('、')
const time = (value) => (value ? new Date(value).toLocaleString() : '—')
const marketText = computed(() => {
  const d = daily.value?.data
  if (!d) return '—'
  return d.latest_date ? `${d.latest_date}，${Number(d.stocks_on_latest).toLocaleString()} / ${Number(d.listed).toLocaleString()} 只股票已更新到这一天` : '还没有行情数据'
})

async function runNow() {
  if (!window.confirm('现在运行今天的每日更新？会在后台下载全市场今天的数据，通常需要十几分钟到一个小时。')) return
  starting.value = true
  try {
    await runDailyUpdate()
    emit('notify', '已开始今天的更新')
    await load()
  } catch (e) {
    emit('notify', e.message || '启动失败')
  } finally {
    starting.value = false
  }
}

async function stop(job) {
  if (!window.confirm('停止这个后台任务？已经下载好的数据会保留，下次可以接着下载。')) return
  try {
    await stopDataJob(job.id)
    emit('notify', '已请求停止，正在收尾')
    await load()
  } catch (e) {
    emit('notify', e.message || '停止失败')
  }
}
</script>

<template>
  <div class="space-y-6">
    <p v-if="error" role="alert" class="rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-200">{{ error }}</p>

    <section class="glass rounded-2xl p-5" aria-label="每天自动更新">
      <div class="flex flex-wrap items-center gap-3">
        <h2 class="text-sm font-semibold text-white">每天自动更新</h2>
        <div class="ml-auto flex gap-2">
          <button type="button" class="rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-xs text-slate-300 hover:text-white" @click="load">刷新</button>
          <button type="button" :disabled="starting || Boolean(running)" class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-1.5 text-xs font-semibold text-white disabled:opacity-50" @click="runNow">
            {{ running ? '有任务在运行' : starting ? '启动中…' : '现在运行今天的更新' }}
          </button>
        </div>
      </div>
      <dl class="mt-4 grid gap-4 text-sm sm:grid-cols-3">
        <div><dt class="text-xs text-slate-400">状态</dt><dd class="mt-1 text-slate-200">{{ daily?.text || '—' }}</dd></div>
        <div><dt class="text-xs text-slate-400">行情数据</dt><dd class="mt-1 text-slate-200">{{ marketText }}</dd></div>
        <div><dt class="text-xs text-slate-400">自动更新时间</dt><dd class="mt-1 text-slate-200">{{ daily ? (daily.enabled ? `每个交易日 ${daily.time} 以后（北京时间）` : '已关闭（FELLOWQUANT_DAILY_UPDATE=off）') : '—' }}</dd></div>
      </dl>
      <div v-if="daily?.last" class="mt-4 rounded-xl border border-white/10 bg-white/5 p-4 text-sm">
        <p class="text-slate-300">上一次：{{ daily.last.trade_date }} · {{ daily.last.trigger === 'auto' ? '自动' : '管理员手动' }} · 完成于 {{ time(daily.last.finished_at) }}</p>
        <p v-if="daily.last.summary" class="mt-1 text-slate-400">{{ daily.last.summary }}</p>
        <ul v-if="daily.last.errors?.length" class="mt-2 space-y-1 text-xs text-amber-200">
          <li v-for="e in daily.last.errors" :key="e">{{ e }}</li>
        </ul>
      </div>
    </section>

    <section v-if="running" class="glass rounded-2xl p-5" aria-label="正在运行的任务">
      <div class="flex flex-wrap items-center gap-3">
        <h2 class="text-sm font-semibold text-white">正在运行</h2>
        <span class="text-xs text-slate-500">{{ datasetText(running) }} · {{ running.start_date }} ~ {{ running.end_date }}</span>
        <button type="button" :disabled="running.stopping" class="ml-auto rounded-full border border-rose-400/30 px-3 py-1 text-xs text-rose-300 hover:bg-rose-400/10 disabled:opacity-50" @click="stop(running)">{{ running.stopping ? '正在停止…' : '停止' }}</button>
      </div>
      <p class="mt-3 text-sm text-slate-300">{{ running.status_label }} · {{ STAGES[running.progress?.stage] || '准备数据' }} · {{ running.progress?.done || 0 }} / {{ running.progress?.total || 0 }}<span v-if="running.progress?.failed" class="text-amber-200"> · 失败 {{ running.progress.failed }}</span></p>
      <div class="mt-2 h-2 overflow-hidden rounded-full bg-white/10" aria-hidden="true">
        <div class="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-500" :style="{ width: `${percent(running.progress)}%` }" />
      </div>
      <p class="mt-2 text-xs text-slate-500">每 5 秒自动刷新。关闭这个页面不影响任务继续运行。</p>
    </section>

    <section class="glass rounded-2xl p-5" aria-label="最近的后台任务">
      <div class="flex flex-wrap items-center gap-3">
        <h2 class="text-sm font-semibold text-white">最近的后台任务</h2>
        <a :href="`${siteBase}/app.html?view=data-update`" class="ml-auto text-xs text-indigo-300 no-underline hover:text-indigo-200">下载历史数据、更新单只股票 → 功能台的数据更新页</a>
      </div>
      <div class="mt-4 overflow-x-auto">
        <table class="[&_td]:whitespace-nowrap [&_th]:whitespace-nowrap [&_td]:px-3 [&_th]:px-3 [&_td:first-child]:pl-0 [&_th:first-child]:pl-0 [&_td:last-child]:pr-0 [&_th:last-child]:pr-0 w-full min-w-[640px] text-left text-sm">
          <thead>
            <tr class="text-xs text-slate-500">
              <th class="pb-3 font-medium">内容</th>
              <th class="pb-3 font-medium">日期范围</th>
              <th class="pb-3 font-medium">状态</th>
              <th class="pb-3 font-medium">开始时间</th>
              <th class="pb-3 font-medium">最后更新</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-white/5">
            <tr v-for="job in recent" :key="job.id" class="text-slate-300">
              <td class="py-3">{{ datasetText(job) }}</td>
              <td class="py-3 text-slate-400">{{ job.start_date }} ~ {{ job.end_date }}</td>
              <td class="py-3" :class="{ 'text-emerald-300': job.status === 'SUCCESS', 'text-amber-300': ['PARTIAL', 'INTERRUPTED', 'STOPPED'].includes(job.status), 'text-rose-300': job.status === 'FAILED' }">{{ job.status_label || job.status }}</td>
              <td class="py-3 text-slate-400">{{ time(job.created_at) }}</td>
              <td class="py-3 text-slate-400">{{ time(job.updated_at) }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="!recent.length" class="py-6 text-center text-sm text-slate-500">还没有后台任务。</p>
      </div>
    </section>
  </div>
</template>
