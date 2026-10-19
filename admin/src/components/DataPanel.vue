<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import {
  backupNow, closedLoopStatus, dailyUpdateStatus, dataJobLog, dataJobs, runDailyUpdate, startDataJob, stopDataJob, systemStatus,
} from '../api.js'
import { bytes, localDate, number, time } from '../format.js'

// 数据更新：服务器空间、每天自动更新的每一步、财务数据、下载历史数据、后台任务和日志、备份。
// 更新单只股票等更细的操作仍在功能台的“数据更新”页。
defineProps({ siteBase: { type: String, default: '' } })
const emit = defineEmits(['notify'])
const daily = ref(null)
const jobs = ref([])
const system = ref(null)
const loop = ref(null)
const error = ref('')
const busy = ref('')
const loaded = ref(false)
let timer = null

const DATASETS = {
  daily: '每日更新', bars: '日线行情', actions: '分红送配', derived: '历史股票池与退市结算', indicators: '估值与换手率',
  fundamentals: '财务数据', industry: '行业分类', index_constituents: '指数成分股', bar_gaps: '补全行情', action_gaps: '补全分红送转记录',
}
const STAGES = {
  market_open: '检查今天是否开市', security_master: '股票列表', daily_bars: '日线行情', corporate_actions: '分红送配', benchmarks: '指数行情',
  index_constituents: '指数成分股', industry: '行业分类', derived: '历史股票池', daily_indicators: '估值与换手率',
  quarterly_fundamentals: '财务数据', bar_gaps: '补全行情', corporate_action_gaps: '补全分红送转记录', universe_membership: '历史股票池',
}
// 可以单独下载的数据；顺序和功能台的数据更新页一致。
const DOWNLOADS = ['bars', 'actions', 'derived', 'indicators', 'fundamentals', 'industry', 'index_constituents']
const ACTIVE = new Set(['STARTING', 'RUNNING', 'RETRYING'])
const FUNDAMENTALS_WINDOW = 450

async function load() {
  error.value = ''
  const [d, j, s, c] = await Promise.allSettled([dailyUpdateStatus(), dataJobs(), systemStatus(), closedLoopStatus()])
  if (d.status === 'fulfilled') daily.value = d.value
  else error.value = d.reason?.message || '加载失败'
  if (j.status === 'fulfilled') jobs.value = j.value.records || []
  if (s.status === 'fulfilled') system.value = s.value
  if (c.status === 'fulfilled') loop.value = c.value
  loaded.value = true
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
const marketText = computed(() => {
  const d = daily.value?.data
  if (!d) return '—'
  return d.latest_date ? `${d.latest_date}，${number(d.stocks_on_latest)} / ${number(d.listed)} 只股票已更新到这一天` : '还没有行情数据'
})

// ---------- 服务器 ----------
const disk = computed(() => system.value?.disk || null)
const diskShare = computed(() => (disk.value?.total ? Math.round((disk.value.used / disk.value.total) * 100) : 0))

// ---------- 每天自动更新 ----------
const lastSteps = computed(() => daily.value?.last?.steps || [])
// 今天的更新有没完成的步骤时，再运行只会重做没完成的部分（已经完成的步骤和股票会跳过）。
const unfinishedToday = computed(() => daily.value?.last?.trade_date === localDate() && lastSteps.value.some((s) => s.state === 'failed'))
async function runNow() {
  const question = unfinishedToday.value
    ? '重新运行今天没完成的部分？已经完成的步骤和股票会跳过。'
    : '现在运行今天的每日更新？会在后台下载全市场今天的数据，通常需要十几分钟到一个小时。'
  if (!window.confirm(question)) return
  await act('daily', async () => {
    await runDailyUpdate()
    emit('notify', '已开始今天的更新')
  })
}

// ---------- 财务数据 ----------
const fundamentals = computed(() => system.value?.fundamentals || null)
const coverageText = computed(() => {
  const f = loop.value?.fundamentals
  if (!f) return '—'
  if (!f.symbols) return '还没有下载'
  const missing = f.missing_symbols ? `；还有 ${number(f.missing_symbols)} 只有行情的股票没有财报` : ''
  return `${number(f.symbols)} 只股票，最新报告期 ${f.latest_stat_date}${missing}`
})
const lastFundamentalsText = computed(() => {
  const last = fundamentals.value?.last
  if (!last) return '还没有自动更新过'
  const outcome = last.result?.quarterly_fundamentals
  const reports = outcome ? `，新增 ${number(outcome.reports)} 份财报${Object.keys(outcome.failed || {}).length ? `，${Object.keys(outcome.failed).length} 只股票没取到` : ''}` : ''
  return `${time(last.finished_at)} · ${statusLabel(last.status)}${reports}`
})
async function updateFundamentals() {
  if (!window.confirm('现在更新最近 5 个报告期的财务数据？只下载还没有的报告期，全市场通常需要半小时到一小时。')) return
  await act('fundamentals', async () => {
    await startDataJob({ start_date: localDate(FUNDAMENTALS_WINDOW), end_date: localDate(), datasets: ['fundamentals'] })
    emit('notify', '已开始更新财务数据')
  })
}

// ---------- 下载历史数据 ----------
const form = reactive({ start_date: localDate(365), end_date: localDate(), datasets: ['bars', 'actions', 'derived'], universeOnly: true })
function toggle(dataset) {
  const at = form.datasets.indexOf(dataset)
  if (at >= 0) form.datasets.splice(at, 1)
  else form.datasets.push(dataset)
}
async function download() {
  if (!form.datasets.length) return emit('notify', '请至少选择一项数据')
  if (!form.start_date || !form.end_date || form.start_date > form.end_date) return emit('notify', '开始日期不能晚于结束日期')
  const names = form.datasets.map((d) => DATASETS[d]).join('、')
  if (!window.confirm(`下载 ${form.start_date} ~ ${form.end_date} 的${names}？已经有的数据会跳过，可以随时停止，下次接着下载。`)) return
  const onlyPool = form.universeOnly && form.datasets.includes('fundamentals')
  await act('download', async () => {
    await startDataJob({ start_date: form.start_date, end_date: form.end_date, datasets: [...form.datasets], ...(onlyPool ? { scope: 'universe' } : {}) })
    emit('notify', '已开始下载')
  })
}

// ---------- 任务和日志 ----------
const statusLabel = (status) => ({ SUCCESS: '完成', PARTIAL: '部分失败', FAILED: '失败', STOPPED: '已停止', INTERRUPTED: '意外中断', RUNNING: '运行中', STARTING: '启动中', RETRYING: '等待重试' }[status] || status || '—')
const logs = reactive({})
async function toggleLog(job) {
  if (logs[job.id] !== undefined) {
    delete logs[job.id]
    return
  }
  logs[job.id] = '加载中…'
  try {
    logs[job.id] = (await dataJobLog(job.id)).log || '（没有日志）'
  } catch (e) {
    logs[job.id] = e.message || '日志加载失败'
  }
}
async function stop(job) {
  if (!window.confirm('停止这个后台任务？已经下载好的数据会保留，下次可以接着下载。')) return
  await act('stop', async () => {
    await stopDataJob(job.id)
    emit('notify', '已请求停止，正在收尾')
  })
}

// ---------- 备份 ----------
const backups = computed(() => system.value?.backups || null)
async function backupNowClick() {
  await act('backup', async () => {
    const data = await backupNow()
    emit('notify', data.name ? `已备份：${data.name}` : '备份完成')
  })
}

async function act(name, work) {
  busy.value = name
  try {
    await work()
    await load()
  } catch (e) {
    emit('notify', e.message || '操作失败')
  } finally {
    busy.value = ''
  }
}

const tableClass = '[&_td]:whitespace-nowrap [&_th]:whitespace-nowrap [&_td]:px-3 [&_th]:px-3 [&_td:first-child]:pl-0 [&_th:first-child]:pl-0 [&_td:last-child]:pr-0 [&_th:last-child]:pr-0 w-full text-left text-sm'
const button = 'rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-xs text-slate-300 hover:text-white disabled:opacity-50'
const primary = 'rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-1.5 text-xs font-semibold text-white disabled:opacity-50'
const stepTone = { done: 'text-emerald-300', failed: 'text-rose-300', skipped: 'text-slate-500' }
const stepMark = { done: '✓', failed: '✗', skipped: '–' }
</script>

<template>
  <div class="space-y-6">
    <p v-if="!loaded" class="text-sm text-slate-400">正在读取数据和服务器状态，第一次打开要几秒钟…</p>
    <p v-if="error" role="alert" class="rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-200">{{ error }}</p>

    <!-- 服务器 -->
    <section v-if="system" class="glass rounded-2xl p-5" aria-label="服务器空间">
      <div class="flex flex-wrap items-center gap-3">
        <h2 class="text-sm font-semibold text-white">服务器空间</h2>
        <button type="button" :class="button" class="ml-auto" @click="load">刷新</button>
      </div>
      <p v-if="disk.warning" role="alert" class="mt-3 rounded-xl border border-rose-400/30 bg-rose-500/10 px-4 py-2.5 text-sm text-rose-200">
        磁盘只剩 {{ bytes(disk.free) }}，空间不够时每日更新和备份会失败。请清理磁盘或换更大的硬盘。
      </p>
      <p class="mt-3 text-sm text-slate-300">已用 {{ bytes(disk.used) }} / 共 {{ bytes(disk.total) }} · 剩余 {{ bytes(disk.free) }}</p>
      <div class="mt-2 h-2 overflow-hidden rounded-full bg-white/10" aria-hidden="true">
        <div class="h-full rounded-full" :class="disk.warning ? 'bg-rose-400' : diskShare >= 80 ? 'bg-amber-400' : 'bg-indigo-400'" :style="{ width: `${diskShare}%` }" />
      </div>
      <dl class="mt-4 grid gap-3 text-sm sm:grid-cols-3">
        <div><dt class="text-xs text-slate-400">行情数据</dt><dd class="mt-1 text-slate-200">{{ bytes(system.sizes.market) }}</dd></div>
        <div><dt class="text-xs text-slate-400">运行记录和任务</dt><dd class="mt-1 text-slate-200">{{ bytes(system.sizes.runtime) }}</dd></div>
        <div><dt class="text-xs text-slate-400">备份</dt><dd class="mt-1 text-slate-200">{{ bytes(system.sizes.backups) }}</dd></div>
      </dl>
    </section>

    <!-- 每天自动更新 -->
    <section class="glass rounded-2xl p-5" aria-label="每天自动更新">
      <div class="flex flex-wrap items-center gap-3">
        <h2 class="text-sm font-semibold text-white">每天自动更新</h2>
        <button type="button" :disabled="busy === 'daily' || Boolean(running)" :class="primary" class="ml-auto" @click="runNow">
          {{ running ? '有任务在运行' : busy === 'daily' ? '启动中…' : unfinishedToday ? '重新运行没完成的部分' : '现在运行今天的更新' }}
        </button>
      </div>
      <dl class="mt-4 grid gap-4 text-sm sm:grid-cols-3">
        <div><dt class="text-xs text-slate-400">状态</dt><dd class="mt-1 text-slate-200">{{ daily?.text || '—' }}</dd></div>
        <div><dt class="text-xs text-slate-400">行情数据</dt><dd class="mt-1 text-slate-200">{{ marketText }}</dd></div>
        <div><dt class="text-xs text-slate-400">自动更新时间</dt><dd class="mt-1 text-slate-200">{{ daily ? (daily.enabled ? `每个交易日 ${daily.time} 以后（北京时间）` : '已关闭（FELLOWQUANT_DAILY_UPDATE=off）') : '—' }}</dd></div>
      </dl>
      <div v-if="daily?.last" class="mt-4 rounded-xl border border-white/10 bg-white/5 p-4 text-sm">
        <p class="text-slate-300">上一次：{{ daily.last.trade_date }} · {{ daily.last.trigger === 'auto' ? '自动' : '管理员手动' }} · {{ statusLabel(daily.last.status) }} · {{ time(daily.last.finished_at) }}</p>
        <ul v-if="lastSteps.length" class="mt-3 grid gap-x-6 gap-y-1.5 sm:grid-cols-2" aria-label="每一步的结果">
          <li v-for="step in lastSteps" :key="step.key" class="flex min-w-0 gap-2">
            <span :class="stepTone[step.state]" aria-hidden="true">{{ stepMark[step.state] }}</span>
            <span class="shrink-0 text-slate-300">{{ step.label }}</span>
            <span class="truncate" :class="step.state === 'failed' ? 'text-rose-300' : 'text-slate-500'" :title="step.text">{{ step.text }}</span>
          </li>
        </ul>
        <p v-if="unfinishedToday" class="mt-3 text-xs text-slate-400">点上面的按钮只会重做没完成的步骤；已经完成的步骤和已经更新好的股票会跳过。</p>
      </div>
    </section>

    <!-- 财务数据 -->
    <section class="glass rounded-2xl p-5" aria-label="财务数据">
      <div class="flex flex-wrap items-center gap-3">
        <h2 class="text-sm font-semibold text-white">财务数据</h2>
        <button type="button" :disabled="busy === 'fundamentals' || Boolean(running)" :class="primary" class="ml-auto" @click="updateFundamentals">现在更新最近的财务数据</button>
      </div>
      <dl class="mt-4 grid gap-4 text-sm sm:grid-cols-3">
        <div><dt class="text-xs text-slate-400">本地的财报</dt><dd class="mt-1 text-slate-200">{{ coverageText }}</dd></div>
        <div><dt class="text-xs text-slate-400">自动更新</dt><dd class="mt-1 text-slate-200">{{ fundamentals?.text || '—' }}</dd></div>
        <div><dt class="text-xs text-slate-400">上一次自动更新</dt><dd class="mt-1 text-slate-200">{{ lastFundamentalsText }}</dd></div>
      </dl>
      <p class="mt-3 text-xs text-slate-500">财报季（1～4 月、7～8 月、10 月，以及 5、9、11 月的第一周）每个周六 10:00 以后自动下载最近 5 个报告期里还没有的财报；平时不会有新财报，不更新。关闭：FELLOWQUANT_FUNDAMENTALS_UPDATE=off。</p>
    </section>

    <!-- 正在运行 -->
    <section v-if="running" class="glass rounded-2xl p-5" aria-label="正在运行的任务">
      <div class="flex flex-wrap items-center gap-3">
        <h2 class="text-sm font-semibold text-white">正在运行</h2>
        <span class="text-xs text-slate-500">{{ datasetText(running) }} · {{ running.start_date }} ~ {{ running.end_date }}</span>
        <button type="button" :disabled="running.stopping || busy === 'stop'" class="ml-auto rounded-full border border-rose-400/30 px-3 py-1 text-xs text-rose-300 hover:bg-rose-400/10 disabled:opacity-50" @click="stop(running)">{{ running.stopping ? '正在停止…' : '停止' }}</button>
      </div>
      <p class="mt-3 text-sm text-slate-300">{{ running.status_label }} · {{ STAGES[running.progress?.stage] || '准备数据' }} · {{ running.progress?.done || 0 }} / {{ running.progress?.total || 0 }}<span v-if="running.progress?.failed" class="text-amber-200"> · 失败 {{ running.progress.failed }}</span></p>
      <div class="mt-2 h-2 overflow-hidden rounded-full bg-white/10" aria-hidden="true">
        <div class="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-500" :style="{ width: `${percent(running.progress)}%` }" />
      </div>
      <p class="mt-2 text-xs text-slate-500">每 5 秒自动刷新。关闭这个页面不影响任务继续运行。</p>
    </section>

    <!-- 下载历史数据 -->
    <section class="glass rounded-2xl p-5" aria-label="下载历史数据">
      <h2 class="text-sm font-semibold text-white">下载历史数据</h2>
      <p class="mt-1 text-xs text-slate-500">选要下载的数据和日期范围。已经有的会跳过，可以随时停止，下次接着下载。同一时间只能运行一个后台任务。</p>
      <div class="mt-4 flex flex-wrap gap-2" role="group" aria-label="要下载的数据">
        <button v-for="d in DOWNLOADS" :key="d" type="button" :aria-pressed="form.datasets.includes(d)"
          class="rounded-full border px-3 py-1 text-xs transition"
          :class="form.datasets.includes(d) ? 'border-indigo-400/50 bg-indigo-500/15 text-white' : 'border-white/10 bg-white/5 text-slate-300 hover:border-white/25'"
          @click="toggle(d)">{{ DATASETS[d] }}</button>
      </div>
      <div class="mt-4 flex flex-wrap items-end gap-3">
        <label class="text-xs text-slate-400">开始日期<input v-model="form.start_date" type="date" class="mt-1 block rounded-xl border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-white outline-none" /></label>
        <label class="text-xs text-slate-400">结束日期<input v-model="form.end_date" type="date" :max="localDate()" class="mt-1 block rounded-xl border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-white outline-none" /></label>
        <label v-if="form.datasets.includes('fundamentals')" class="flex items-center gap-2 pb-1.5 text-xs text-slate-300">
          <input v-model="form.universeOnly" type="checkbox" class="h-4 w-4 accent-indigo-500" />财务数据只下载我的股票池（全市场的多年历史要十几个小时）
        </label>
        <button type="button" :disabled="busy === 'download' || Boolean(running)" :class="primary" class="ml-auto" @click="download">开始下载</button>
      </div>
    </section>

    <!-- 最近的后台任务 -->
    <section class="glass rounded-2xl p-5" aria-label="最近的后台任务">
      <div class="flex flex-wrap items-center gap-3">
        <h2 class="text-sm font-semibold text-white">最近的后台任务</h2>
        <a :href="`${siteBase}/app.html?view=data-update`" class="ml-auto text-xs text-indigo-300 no-underline hover:text-indigo-200">更新单只股票等 → 功能台的数据更新页</a>
      </div>
      <div class="mt-4 overflow-x-auto">
        <table :class="tableClass" class="min-w-[760px]">
          <thead>
            <tr class="text-xs text-slate-500">
              <th class="pb-3 font-medium">内容</th>
              <th class="pb-3 font-medium">日期范围</th>
              <th class="pb-3 font-medium">状态</th>
              <th class="pb-3 font-medium">来源</th>
              <th class="pb-3 font-medium">开始时间</th>
              <th class="pb-3 font-medium">最后更新</th>
              <th class="pb-3 text-right font-medium">日志</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-white/5">
            <template v-for="job in recent" :key="job.id">
              <tr class="text-slate-300">
                <td class="py-3">{{ datasetText(job) }}</td>
                <td class="py-3 text-slate-400">{{ job.start_date }} ~ {{ job.end_date }}</td>
                <td class="py-3" :class="{ 'text-emerald-300': job.status === 'SUCCESS', 'text-amber-300': ['PARTIAL', 'INTERRUPTED', 'STOPPED'].includes(job.status), 'text-rose-300': job.status === 'FAILED' }">{{ job.status_label || statusLabel(job.status) }}</td>
                <td class="py-3 text-slate-400">{{ job.trigger === 'auto' ? '自动' : '手动' }}</td>
                <td class="py-3 text-slate-400">{{ time(job.created_at) }}</td>
                <td class="py-3 text-slate-400">{{ time(job.updated_at) }}</td>
                <td class="py-3 text-right"><button type="button" class="rounded-full border border-white/10 px-3 py-0.5 text-xs text-slate-300 hover:text-white" @click="toggleLog(job)">{{ logs[job.id] !== undefined ? '收起' : '查看' }}</button></td>
              </tr>
              <tr v-if="logs[job.id] !== undefined">
                <td colspan="7" class="pb-3">
                  <pre class="max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-xl border border-white/10 bg-black/30 p-3 font-mono text-[11px] leading-relaxed text-slate-300">{{ logs[job.id] }}</pre>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
        <p v-if="!recent.length" class="py-6 text-center text-sm text-slate-500">还没有后台任务。</p>
      </div>
    </section>

    <!-- 备份 -->
    <section v-if="backups" class="glass rounded-2xl p-5" aria-label="备份">
      <div class="flex flex-wrap items-center gap-3">
        <h2 class="text-sm font-semibold text-white">账户数据备份</h2>
        <button type="button" :disabled="busy === 'backup'" :class="primary" class="ml-auto" @click="backupNowClick">{{ busy === 'backup' ? '备份中…' : '立即备份' }}</button>
      </div>
      <p class="mt-1 text-xs text-slate-500">{{ backups.enabled ? `每天自动备份一次，保留最近 ${backups.keep} 份；手动备份另外保留最近 5 份。` : '自动备份已关闭（FELLOWQUANT_BACKUP=off），可以手动备份。' }}升级或迁移服务器前建议先手动备份一次。行情数据不备份，可以重新下载。</p>
      <ul v-if="backups.items.length" class="mt-4 divide-y divide-white/5 text-sm">
        <li v-for="item in backups.items.slice(0, 10)" :key="item.name" class="flex items-center justify-between py-2">
          <span class="font-mono text-xs text-slate-300">{{ item.name }}<span v-if="item.manual" class="ml-2 font-sans text-indigo-300">手动</span></span>
          <span class="text-xs text-slate-500">{{ bytes(item.size) }}</span>
        </li>
      </ul>
      <p v-else class="mt-4 text-sm text-slate-500">还没有备份。</p>
    </section>
  </div>
</template>
