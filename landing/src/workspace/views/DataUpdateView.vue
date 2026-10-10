<script setup>
import { computed, onActivated, onBeforeUnmount, onDeactivated, reactive, ref } from 'vue'
import {
  closedLoopStatus,
  dataJobLog,
  dataJobs,
  dataOverview,
  dataUpdate,
  startDataJob,
  stopDataJob,
} from '../../api.js'
import MetricCard from '../ui/MetricCard.vue'
import SectionCard from '../ui/SectionCard.vue'
import DataTable from '../ui/DataTable.vue'
import FormField from '../ui/FormField.vue'
import StatusPill from '../ui/StatusPill.vue'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

// ===========================================================================
// 日常更新（自原数据资产页迁移；来源顺序/基准多选保持不变）
// ===========================================================================
function localIso(d) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}
const today = new Date()
const oneYearAgo = new Date(today)
oneYearAgo.setFullYear(today.getFullYear() - 1)

const overview = ref(null)
const overviewLoading = ref(true)
const overviewError = ref('')
const updateError = ref('')
const updateAttempted = ref(false)
const advancedOpen = ref(false)
function navigate(key) {
  window.dispatchEvent(new CustomEvent('fq-navigate', { detail: key }))
}
const providers = computed(() => overview.value?.providers || [])
const providerLabel = (id) => {
  const hit = providers.value.find((p) => p.provider === id)
  return hit ? hit.display_name : id
}

const form = reactive({
  start_date: localIso(oneYearAgo),
  end_date: localIso(today),
  include_security_master: true,
  include_market: true,
  include_benchmark: true,
  benchmark_symbols: [],
  market_source: 'auto',
  allow_fallback: true,
})

const sourceOptions = computed(() => {
  const opts = [{ value: 'auto', label: `自动推荐（${providers.value.map((p) => p.display_name).join(' → ')}）` }]
  for (const p of providers.value) opts.push({ value: p.provider, label: p.display_name })
  return opts
})
const selectedSourceNotReady = computed(() => {
  if (form.market_source === 'auto') return false
  const hit = providers.value.find((p) => p.provider === form.market_source)
  return hit ? hit.readiness !== 'READY' : false
})

const benchmarkEntries = computed(() =>
  Object.entries(overview.value?.benchmarks || {}).map(([name, symbol]) => ({ name, symbol }))
)
function toggleBenchmark(name) {
  const idx = form.benchmark_symbols.indexOf(name)
  if (idx >= 0) form.benchmark_symbols.splice(idx, 1)
  else form.benchmark_symbols.push(name)
}

const updating = ref(false)
const updateResults = ref([])
const datasetLabels = {
  security_master: '证券主表',
  daily_bars: '配置股票池行情',
  benchmark_bars: '基准指数',
}
const updateCols = [
  { key: 'dataset', label: '数据集' },
  { key: 'status', label: '状态' },
  { key: 'rows', label: '记录数', align: 'right' },
  { key: 'message', label: '结果' },
]
const updateRows = computed(() =>
  (updateResults.value || []).map((r) => ({
    dataset: datasetLabels[r.dataset] || r.dataset,
    status: r.status,
    rows: r.rows != null ? Number(r.rows).toLocaleString() : '—',
    message: r.error ? `${r.message || ''}（${r.error}）` : r.message || '—',
    failed: r.status === 'FAILED',
  }))
)

async function loadOverview() {
  overviewLoading.value = true
  overviewError.value = ''
  try {
    overview.value = await dataOverview()
    if (!form.benchmark_symbols.length) {
      const hit = benchmarkEntries.value.find((b) => b.symbol === overview.value.benchmark_symbol)
      if (hit) form.benchmark_symbols = [hit.name]
    }
  } catch (e) {
    overviewError.value = e.message || '加载数据概览失败'
    props.notify(e.message || '加载数据概览失败')
  } finally {
    overviewLoading.value = false
  }
}

async function runUpdate() {
  if (updating.value) return
  if (!form.start_date || !form.end_date) return props.notify('请选择开始与结束日期')
  if (form.start_date > form.end_date) return props.notify('开始日期不能晚于结束日期')
  if (!form.include_market && !form.include_security_master && !form.include_benchmark) return props.notify('请至少选择一类更新数据')
  updating.value = true
  updateAttempted.value = true
  updateError.value = ''
  updateResults.value = []
  try {
    const payload = {
      start_date: form.start_date,
      end_date: form.end_date,
      include_security_master: form.include_security_master,
      include_market: form.include_market,
      include_benchmark: form.include_benchmark,
      allow_market_fallback: form.allow_fallback,
    }
    if (form.market_source !== 'auto') {
      const order = [form.market_source]
      if (form.allow_fallback) {
        order.push(...providers.value.map((p) => p.provider).filter((p) => p !== form.market_source))
      }
      payload.market_source_order = order
    }
    if (form.benchmark_symbols.length) payload.benchmark_symbols = [...form.benchmark_symbols]
    const data = await dataUpdate(payload)
    updateResults.value = data.results || []
    const failed = updateResults.value.filter((r) => r.status !== 'SUCCESS').length
    props.notify(!updateResults.value.length ? '未返回更新结果，请核对数据状态' : failed ? `更新返回，${failed} 项需核对` : '数据更新完成')
    await loadOverview()
  } catch (e) {
    updateError.value = e.message || '数据更新失败'
    props.notify(e.message || '数据更新失败')
  } finally {
    updating.value = false
  }
}

// ===========================================================================
// 全市场回填任务（迁移自 AlphaQuant data_job_panel.py：detached 后台作业）
// ===========================================================================
const STAGES = {
  security_master: '证券主表',
  daily_bars: '日线行情',
  corporate_actions: '分红送配',
  universe_membership: '历史股票池',
  delisting_settlements: '退市结算',
}
const INCOMPLETE = ['FAILED', 'PARTIAL', 'STOPPED', 'INTERRUPTED']

const jobs = ref([])
const jobsLoading = ref(false)
const jobsError = ref('')
const activeJob = computed(() =>
  jobs.value.find((j) => ['STARTING', 'RUNNING', 'RETRYING'].includes(j.status))
)
const selectedJobId = ref('')
const selectedJob = computed(() => jobs.value.find((j) => j.id === selectedJobId.value) || null)
const showLog = ref(false)
const logText = ref('')

const jobForm = reactive({
  start_date: '2015-01-01',
  end_date: localIso(today),
  datasets: ['bars', 'actions', 'derived'],
})
const DATASET_OPTIONS = [
  { value: 'bars', label: '日线行情' },
  { value: 'actions', label: '分红送配' },
  { value: 'derived', label: '历史股票池与退市结算' },
]
function toggleDataset(v) {
  const idx = jobForm.datasets.indexOf(v)
  if (idx >= 0) jobForm.datasets.splice(idx, 1)
  else jobForm.datasets.push(v)
}

const historyCols = [
  { key: 'label', label: '任务' },
  { key: 'status', label: '状态' },
  { key: 'created_at', label: '创建时间' },
  { key: 'retries', label: '重试次数', align: 'right' },
]
// 任务状态 -> StatusPill 颜色档位（原值展示中文标签）
function jobPillValue(status) {
  if (['SUCCESS'].includes(status)) return 'SUCCESS'
  if (['FAILED', 'STOPPED', 'INTERRUPTED'].includes(status)) return 'FAILED'
  if (['PARTIAL', 'RETRYING'].includes(status)) return 'WARNING'
  return status
}

const historyRows = computed(() =>
  jobs.value.map((r) => ({
    id: r.id,
    label: `${r.start_date} 至 ${r.end_date}`,
    status: r.status_label || r.status,
    pill: jobPillValue(r.status),
    created_at: r.created_at,
    retries: r.retries ?? 0,
  }))
)

const progressPct = computed(() => {
  const p = activeJob.value?.progress || {}
  if (!p.total) return 0
  return Math.min(100, Math.round((p.done / p.total) * 100))
})

async function loadJobs() {
  jobsLoading.value = true
  jobsError.value = ''
  try {
    const data = await dataJobs()
    jobs.value = data.records || []
    if (jobs.value.length && !selectedJobId.value) selectedJobId.value = jobs.value[0].id
    if (!jobs.value.some((j) => j.id === selectedJobId.value)) {
      selectedJobId.value = jobs.value[0]?.id || ''
      showLog.value = false
    }
  } catch (e) {
    jobsError.value = e.message || '加载任务列表失败'
    props.notify(e.message || '加载任务列表失败')
  } finally {
    jobsLoading.value = false
  }
}

async function startJob(payload) {
  try {
    await startDataJob(payload)
    props.notify('全市场回填任务已启动')
    await loadJobs()
    schedulePoll()
    showLog.value = true
  } catch (e) {
    props.notify(e.message || '启动任务失败')
  }
}

async function submitJob() {
  if (!jobForm.start_date || !jobForm.end_date) return props.notify('请选择回填日期范围')
  if (!jobForm.datasets.length) return props.notify('请至少选择一个回填数据集')
  await startJob({
    start_date: jobForm.start_date,
    end_date: jobForm.end_date,
    datasets: [...jobForm.datasets],
  })
}

async function resumeJob(job) {
  await startJob({
    start_date: job.start_date,
    end_date: job.end_date,
    datasets: job.datasets || ['bars', 'actions', 'derived'],
  })
}

async function stopActive() {
  if (!activeJob.value) return
  try {
    await stopDataJob(activeJob.value.id)
    props.notify('已请求停止，等待当前批次安全结束')
    await loadJobs()
  } catch (e) {
    props.notify(e.message || '停止任务失败')
  }
}

async function loadLog() {
  if (!selectedJobId.value) return
  try {
    const data = await dataJobLog(selectedJobId.value)
    logText.value = data.log || '暂无日志'
  } catch (e) {
    logText.value = `读取日志失败：${e.message}`
  }
}

function toggleJobLog() {
  showLog.value = !showLog.value
  if (showLog.value) loadLog()
}

// 有活跃任务时每 5 秒轮询进度（迁移自 Streamlit fragment run_every="5s"）
let pollTimer = null
let viewActive = false
function schedulePoll() {
  if (pollTimer || !activeJob.value || !viewActive) return
  pollTimer = setInterval(async () => {
    await loadJobs()
    if (showLog.value && activeJob.value) loadLog()
    if (!activeJob.value && pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }, 5000)
}

// ===========================================================================
// 闭环落地状态（只读汇总五张表与断点进度）
// ===========================================================================
const loop = ref(null)
const loopError = ref('')
const loopLoading = ref(false)
const CHECKPOINT_LABELS = {
  security_master: '证券主表',
  daily_bars: '日线行情',
  corporate_actions: '分红送配',
  universe_membership: '历史股票池',
  delisting_settlements: '退市结算',
}
const loopMetrics = computed(() => {
  const s = loop.value
  if (!s) return []
  return [
    { label: '证券主表标的', value: s.master_total != null ? Number(s.master_total).toLocaleString() : '—', sub: `其中已退市 ${Number(s.master_delisted || 0).toLocaleString()}` },
    { label: '行情覆盖标的', value: s.bars_symbols != null ? Number(s.bars_symbols).toLocaleString() : '—', sub: `${Number(s.bars_rows || 0).toLocaleString()} 条记录` },
    { label: '行情区间', value: s.bars_min ? `${s.bars_min} ~ ${s.bars_max}` : '—', sub: '本地最早/最晚交易日' },
    { label: '历史股票池', value: s.membership_rows != null ? Number(s.membership_rows).toLocaleString() : '—', sub: `${Number(s.membership_symbols || 0).toLocaleString()} 个标的` },
    { label: '退市结算记录', value: s.settlement_rows != null ? Number(s.settlement_rows).toLocaleString() : '—', sub: '推导值' },
    { label: '分红送配记录', value: s.corporate_action_rows != null ? Number(s.corporate_action_rows).toLocaleString() : '—', sub: '公司行为事件' },
  ]
})
const checkpointRows = computed(() =>
  Object.entries(loop.value?.checkpoint || {}).map(([dataset, c]) => ({
    dataset: CHECKPOINT_LABELS[dataset] || dataset,
    range: c.range || '—',
    done: c.done ?? 0,
    failed: c.failed ?? 0,
    updated_at: c.updated_at || '—',
    warn: (c.failed || 0) > 0,
  }))
)

async function loadLoop() {
  if (loopLoading.value) return
  loopLoading.value = true
  loopError.value = ''
  try {
    loop.value = await closedLoopStatus()
  } catch (e) {
    loopError.value = e.message || '读取闭环状态失败'
  } finally {
    loopLoading.value = false
  }
}

function toggleAdvanced(event) {
  advancedOpen.value = event.target.open
  if (advancedOpen.value && !loop.value) loadLoop()
}
function clearPoll() {
  viewActive = false
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
}
onActivated(async () => {
  viewActive = true
  await Promise.all([loadOverview(), loadJobs()])
  schedulePoll()
})
onDeactivated(clearPoll)
onBeforeUnmount(clearPoll)
</script>

<template>
  <div class="space-y-6">
    <!-- 标题 -->
    <div class="glass relative overflow-hidden rounded-2xl p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-indigo-500/20 blur-3xl" />
      <h1 class="text-xl font-bold text-white">数据更新</h1>
      <p class="mt-1 text-sm text-slate-400">日常只需更新当前股票池。需要全市场历史数据时，再展开高级更新。</p>
    </div>

    <!-- 日常更新 -->
    <SectionCard title="更新当前股票池" hint="默认同步股票池行情、股票信息和基准指数；可在下方调整">
      <p class="text-sm text-slate-300">{{ overviewLoading ? '正在读取股票池…' : overview ? `当前股票池 ${overview.configured_symbol_count} 只股票` : '股票池信息暂时不可用' }} · {{ form.start_date }} 至 {{ form.end_date }}</p>
      <p class="mt-2 text-sm text-slate-400">默认更新近一年行情，保留已有历史数据。首次研究更早的区间，可在下方调整日期。</p>
      <p v-if="overviewError" class="mt-3 text-sm text-rose-300">{{ overviewError }} <button type="button" class="underline" @click="loadOverview">重新读取</button></p>
      <section class="mt-4 rounded-xl border border-white/10 p-4" aria-labelledby="daily-update-options">
        <h3 id="daily-update-options" class="text-sm font-medium text-slate-300">调整日期、更新内容与来源</h3>
        <div class="mt-4">
          <div class="grid gap-4 md:grid-cols-2">
            <FormField label="开始日期" type="date" v-model="form.start_date" />
            <FormField label="结束日期" type="date" v-model="form.end_date" />
          </div>

          <div class="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2">
            <label class="flex items-center gap-2.5">
              <input v-model="form.include_security_master" type="checkbox" class="h-4 w-4 rounded border-white/20 bg-white/5 accent-indigo-500" />
              <span class="text-sm text-slate-300">更新全A证券主表</span>
            </label>
            <label class="flex items-center gap-2.5">
              <input v-model="form.include_market" type="checkbox" class="h-4 w-4 rounded border-white/20 bg-white/5 accent-indigo-500" />
              <span class="text-sm text-slate-300">更新配置股票池行情</span>
            </label>
            <label class="flex items-center gap-2.5">
              <input v-model="form.include_benchmark" type="checkbox" class="h-4 w-4 rounded border-white/20 bg-white/5 accent-indigo-500" />
              <span class="text-sm text-slate-300">更新基准指数</span>
            </label>
          </div>

          <p class="mt-3 rounded-xl bg-indigo-500/10 px-3 py-2 text-xs text-indigo-300">
            行情只更新当前股票池；全市场历史数据请使用下方「高级更新」。证券主表和基准指数使用 AkShare，XTick 暂不支持批量行情更新。
          </p>

          <!-- 基准指数多选 -->
          <div v-if="benchmarkEntries.length" class="mt-4">
            <span class="mb-1.5 block text-xs text-slate-400">基准指数（可多选）</span>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="b in benchmarkEntries"
                :key="b.symbol"
                type="button"
                class="rounded-full border px-3 py-1.5 text-xs font-medium transition"
                :class="form.benchmark_symbols.includes(b.name)
                  ? 'border-indigo-400/60 bg-indigo-500/20 text-indigo-200'
                  : 'border-white/10 bg-white/5 text-slate-400 hover:border-white/20 hover:text-slate-300'"
                @click="toggleBenchmark(b.name)"
              >
                {{ b.name }}
              </button>
            </div>
            <p class="mt-1.5 text-xs text-slate-500">用于净值对齐与相对收益计算；不选择则使用配置默认基准。</p>
          </div>

          <div class="mt-4 grid gap-4 md:grid-cols-2">
            <FormField label="股票日线行情来源" type="select" v-model="form.market_source" :options="sourceOptions" hint="指定来源只影响本次更新，不修改全局默认配置" />
            <label class="flex items-center gap-2.5 pt-1">
              <input v-model="form.allow_fallback" type="checkbox" class="h-4 w-4 rounded border-white/20 bg-white/5 accent-indigo-500" />
              <span class="text-sm text-slate-300">首选来源失败时自动尝试其他来源</span>
            </label>
          </div>

          <p v-if="selectedSourceNotReady" class="mt-3 rounded-xl bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
            {{ providerLabel(form.market_source) }} 当前未就绪。如保留自动回退，系统仍会尝试其他来源。
          </p>

        </div>
      </section>
      <div class="mt-5 flex flex-wrap items-center gap-3">
        <button
          @click="runUpdate"
          :disabled="updating || overviewLoading || !!overviewError || !overview || (form.include_market && !overview.configured_symbol_count)"
          class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
        >
          {{ updating ? '更新中…' : '开始更新' }}
        </button>
        <button type="button" class="px-3 py-2 text-sm text-indigo-300 hover:underline" @click="navigate('universe')">调整股票池</button>
        <button type="button" class="px-3 py-2 text-sm text-slate-400 hover:underline" @click="navigate('data-management')">查看数据概览</button>
      </div>
      <p v-if="updating" class="mt-4 text-sm text-slate-400" role="status">正在更新数据，请保持页面打开。完成后会显示结果。</p>
      <p v-if="updateError" class="mt-4 text-sm text-rose-300" role="alert">{{ updateError }}</p>
      <p v-if="updateAttempted && !updating && !updateError && !updateResults.length" class="mt-4 text-sm text-amber-300" role="status">未返回更新结果，请到数据概览核对，或重新尝试。</p>

      <div v-if="updateResults.length" class="mt-6">
        <p class="mb-3 text-sm text-slate-300" role="status">{{ updateResults.every((r) => r.status === 'SUCCESS') ? '本次更新完成。' : '本次更新存在未成功项目，请查看下方结果。' }}</p>
        <DataTable :columns="updateCols" :rows="updateRows" empty="暂无更新记录">
          <template #cell-status="{ row }">
            <StatusPill :value="row.status" />
          </template>
          <template #cell-message="{ row }">
            <span :class="row.failed ? 'text-rose-300' : 'text-slate-300'">{{ row.message }}</span>
          </template>
        </DataTable>
      </div>
    </SectionCard>
    <p v-if="jobsError" class="text-sm text-rose-300">{{ jobsError }} <button type="button" class="underline" @click="loadJobs">重试读取任务</button></p>
    <section v-if="activeJob" class="glass rounded-2xl p-5" aria-label="后台更新进度">
      <h2 class="mb-4 text-sm font-semibold text-white">全市场回填正在后台运行</h2>
      <p class="mb-4 text-sm text-slate-400">关闭页面不影响后台回填；可随时在高级更新中查看记录和日志。</p>
      <!-- 活跃任务进度 -->
      <div v-if="activeJob" class="mb-6 rounded-xl border border-indigo-400/20 bg-indigo-500/5 p-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <p class="text-sm font-medium text-indigo-200">
            {{ activeJob.status_label }} · {{ STAGES[activeJob.progress?.stage] || '准备数据' }} ·
            {{ activeJob.progress?.done || 0 }} / {{ activeJob.progress?.total || 0 }}
          </p>
          <button
            v-if="!activeJob.stopping"
            type="button"
            class="rounded-full border border-rose-400/30 bg-rose-500/10 px-4 py-1.5 text-xs text-rose-200 transition hover:bg-rose-500/20"
            @click="stopActive"
          >停止任务</button>
        </div>
        <div class="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-white/10">
          <div class="h-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-500" :style="{ width: `${progressPct}%` }" />
        </div>
        <p class="mt-2 text-xs text-slate-500">
          最近进展：{{ activeJob.progress?.updated_at || '等待首批数据' }} · 本阶段失败：{{
            activeJob.progress?.failed || 0
          }} · 自动重试：{{ activeJob.retries || 0 }} 次
        </p>
        <p v-if="activeJob.stopping" class="mt-2 rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
          已请求停止，等待当前批次安全结束；数据源卡死时等待看门狗退出。
        </p>
      </div>

    </section>
    <details class="glass rounded-2xl p-5" :open="advancedOpen" @toggle="toggleAdvanced">
      <summary class="cursor-pointer text-lg font-semibold text-white">高级更新：历史回填、任务记录与日志</summary>
      <div class="mt-5 space-y-6">
        <!-- 全市场回填任务（迁移自 AlphaQuant data_job_panel） -->
        <SectionCard title="全市场历史回填" hint="退市股、历史成分与断点续传；任务在后台独立进程执行">
          <!-- 启动表单 -->
          <div v-if="!activeJob" class="space-y-4">
            <div class="grid gap-4 md:grid-cols-2">
              <FormField label="回填开始日期" type="date" v-model="jobForm.start_date" />
              <FormField label="回填结束日期" type="date" v-model="jobForm.end_date" />
            </div>
            <div>
              <span class="mb-1.5 block text-xs text-slate-400">回填数据（可多选）</span>
              <div class="flex flex-wrap gap-2">
                <button
                  v-for="d in DATASET_OPTIONS"
                  :key="d.value"
                  type="button"
                  class="rounded-full border px-3 py-1.5 text-xs font-medium transition"
                  :class="jobForm.datasets.includes(d.value)
                    ? 'border-indigo-400/60 bg-indigo-500/20 text-indigo-200'
                    : 'border-white/10 bg-white/5 text-slate-400 hover:border-white/20 hover:text-slate-300'"
                  @click="toggleDataset(d.value)"
                >
                  {{ d.label }}
                </button>
              </div>
            </div>
            <div class="flex flex-wrap items-center gap-3">
              <button
                type="button"
                :disabled="!jobForm.datasets.length"
                class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
                @click="submitJob"
              >启动回填</button>
              <span class="text-xs text-slate-500">同一区间会自动跳过已完成部分；失败后最多自动重试 20 次</span>
            </div>
            <p class="rounded-xl bg-white/5 px-3 py-2 text-xs text-slate-500">
              证券主表始终更新；历史股票池按上市退市规则近似生成，退市结算为推导值。
            </p>
          </div>

          <!-- 历史记录 -->
          <div v-if="jobs.length" class="mt-6">
            <DataTable :columns="historyCols" :rows="historyRows" empty="暂无任务记录">
              <template #cell-label="{ row }">
                <button type="button" class="text-left text-indigo-300 transition hover:text-indigo-200" @click="selectedJobId = row.id; showLog = false">
                  {{ row.label }}
                </button>
              </template>
              <template #cell-status="{ row }">
                <StatusPill :value="row.pill" :text="row.status" />
              </template>
            </DataTable>

            <!-- 选中任务：继续回填 + 日志 -->
            <div v-if="selectedJob" class="mt-4 rounded-xl border border-white/10 bg-white/5 p-4">
              <div class="flex flex-wrap items-center justify-between gap-3">
                <p class="text-sm text-slate-300">
                  {{ selectedJob.start_date }} 至 {{ selectedJob.end_date }} ·
                  <span class="text-slate-500">{{ selectedJob.id }}</span>
                </p>
                <div class="flex items-center gap-2">
                  <button
                    v-if="INCOMPLETE.includes(selectedJob.status) && !activeJob"
                    type="button"
                    class="rounded-full border border-indigo-400/30 bg-indigo-500/10 px-4 py-1.5 text-xs text-indigo-200 transition hover:bg-indigo-500/20"
                    @click="resumeJob(selectedJob)"
                  >继续回填</button>
                  <button
                    type="button"
                    class="rounded-full border border-white/10 px-4 py-1.5 text-xs text-slate-300 transition hover:bg-white/5"
                    @click="toggleJobLog"
                  >{{ showLog ? '收起日志' : '最近日志（最多 32 KB）' }}</button>
                </div>
              </div>
              <p v-if="INCOMPLETE.includes(selectedJob.status)" class="mt-2 text-xs text-amber-300">
                任务尚未全部完成，可按原日期和数据范围继续回填。
              </p>
              <pre
                v-if="showLog"
                class="mt-3 max-h-80 overflow-auto rounded-lg bg-black/40 p-3 text-xs leading-relaxed text-slate-400"
              >{{ logText || '暂无日志' }}</pre>
            </div>
          </div>
          <p v-else-if="!jobsLoading && !jobsError" class="text-xs text-slate-500">暂无后台回填任务记录。</p>
        </SectionCard>

        <!-- 闭环落地状态 -->
        <SectionCard title="全市场数据闭环状态" hint="只读汇总五张核心表的落地情况与断点进度，不访问外网">
          <p v-if="loopLoading" class="text-sm text-slate-400">正在读取全市场统计…</p>
          <div v-else-if="loopError" class="rounded-xl bg-rose-500/10 px-3 py-2 text-sm text-rose-300">{{ loopError }} <button type="button" class="underline" @click="loadLoop">重试</button></div>
          <template v-else>
            <section class="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
              <MetricCard v-for="m in loopMetrics" :key="m.label" :label="m.label" :value="m.value" :sub="m.sub" />
            </section>
            <div v-if="checkpointRows.length" class="mt-5">
              <p class="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">断点进度</p>
              <DataTable
                :columns="[
                  { key: 'dataset', label: '数据集' },
                  { key: 'range', label: '区间' },
                  { key: 'done', label: '已完成标的', align: 'right' },
                  { key: 'failed', label: '失败标的', align: 'right' },
                  { key: 'updated_at', label: '更新时间' },
                ]"
                :rows="checkpointRows"
                empty="暂无断点记录"
              >
                <template #cell-failed="{ row }">
                  <span :class="row.warn ? 'text-rose-300' : 'text-slate-300'">{{ row.failed }}</span>
                </template>
              </DataTable>
            </div>
          </template>
        </SectionCard>

      </div>
    </details>
  </div>
</template>
