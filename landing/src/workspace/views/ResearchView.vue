<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { researchBaselines, runOptimization, runWalkForward } from '../../api.js'
import DataTable from '../ui/DataTable.vue'
import EmptyState from '../ui/EmptyState.vue'
import MetricCard from '../ui/MetricCard.vue'
import SectionCard from '../ui/SectionCard.vue'
import StatusPill from '../ui/StatusPill.vue'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

const objectiveOptions = [
  { value: 'sharpe', label: '夏普比率' },
  { value: 'annual_return', label: '年化收益' },
  { value: 'calmar', label: '卡玛比率' },
  { value: 'max_drawdown', label: '最大回撤最小' },
]

// ---------- 基准回测 ----------
const baselines = ref([])
const baselineLoading = ref(false)
const baselineRunId = ref('')

async function loadBaselines() {
  baselineLoading.value = true
  try {
    const data = await researchBaselines()
    baselines.value = data.items || []
    if (baselines.value.length && !baselineRunId.value) {
      baselineRunId.value = baselines.value[0].run_id
    }
  } catch (e) {
    props.notify(e.message || '加载基线失败')
  } finally {
    baselineLoading.value = false
  }
}

// ---------- 参数候选值解析 ----------
function parseCandidates(raw) {
  return String(raw || '')
    .split(/[,，]/)
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => {
      const n = Number(s)
      return Number.isNaN(n) ? s : n
    })
}

// ---------- 参数优化 ----------
const opt = reactive({
  param1Name: 'window',
  param1Values: '10,20,30',
  param2Name: 'threshold',
  param2Values: '0.0,0.05',
  objective: 'sharpe',
  maxDrawdownLimit: 0.3,
  running: false,
})
const optResult = ref(null)
const optError = ref('')

function buildParameterGrid() {
  const grid = {}
  const entries = [
    { name: opt.param1Name, raw: opt.param1Values },
    { name: opt.param2Name, raw: opt.param2Values },
  ]
  for (const e of entries) {
    const name = String(e.name || '').trim()
    if (!name) continue
    const values = parseCandidates(e.raw)
    if (!values.length) continue
    grid[name] = values
  }
  return grid
}

async function onOptimize() {
  if (baselineRunId.value === '' || baselineRunId.value === null) return props.notify('请先选择基准回测')
  const grid = buildParameterGrid()
  if (!Object.keys(grid).length) return props.notify('请至少填写一组有效的参数候选值')
  opt.running = true
  optError.value = ''
  optResult.value = null
  try {
    optResult.value = await runOptimization({
      baseline_run_id: baselineRunId.value,
      parameter_grid: grid,
      objective: opt.objective,
      max_drawdown_limit: Number(opt.maxDrawdownLimit) || 0,
    })
    props.notify('参数优化完成')
  } catch (e) {
    optError.value = e.message || '参数优化失败'
    props.notify(optError.value)
  } finally {
    opt.running = false
  }
}

const optColumns = [
  { key: 'rank', label: '排名', align: 'right' },
  { key: 'eligible', label: '是否合格' },
  { key: 'objective_value', label: '目标值', align: 'right' },
  { key: 'max_drawdown', label: '最大回撤', align: 'right' },
  { key: 'parameters', label: '参数' },
  { key: 'status', label: '状态' },
]

const optEligibleCount = computed(() =>
  (optResult.value?.results || []).filter((r) => r.eligible).length
)

// ---------- 滚动样本外验证 ----------
const wf = reactive({
  objective: 'sharpe',
  trainingMonths: 12,
  testMonths: 3,
  stepMonths: 3,
  maxWindows: 8,
  running: false,
})
const wfResult = ref(null)
const wfError = ref('')

async function onWalkForward() {
  if (baselineRunId.value === '' || baselineRunId.value === null) return props.notify('请先选择基准回测')
  const grid = buildParameterGrid()
  if (!Object.keys(grid).length) return props.notify('请至少填写一组有效的参数候选值')
  wf.running = true
  wfError.value = ''
  wfResult.value = null
  try {
    wfResult.value = await runWalkForward({
      baseline_run_id: baselineRunId.value,
      parameter_grid: grid,
      objective: wf.objective,
      training_months: Number(wf.trainingMonths) || 12,
      test_months: Number(wf.testMonths) || 3,
      step_months: Number(wf.stepMonths) || 3,
      max_windows: Number(wf.maxWindows) || 8,
    })
    props.notify('滚动验证完成')
  } catch (e) {
    wfError.value = e.message || '滚动验证失败'
    props.notify(wfError.value)
  } finally {
    wf.running = false
  }
}

const wfColumns = [
  { key: 'window', label: '窗口', align: 'right' },
  { key: 'train_range', label: '训练区间' },
  { key: 'test_range', label: '测试区间' },
  { key: 'test_cumulative_return', label: '样本外收益', align: 'right' },
  { key: 'test_max_drawdown', label: '回撤', align: 'right' },
  { key: 'status', label: '状态' },
]

const wfRows = computed(() =>
  (wfResult.value?.windows || []).map((w) => ({
    ...w,
    train_range: `${w.train_start} ~ ${w.train_end}`,
    test_range: `${w.test_start} ~ ${w.test_end}`,
  }))
)

// ---------- 格式化 ----------
function toNum(v) {
  const n = Number(v)
  return Number.isNaN(n) ? 0 : n
}

function fmtNum(v, pct = false, digits = 2) {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  if (Number.isNaN(n)) return v
  return pct ? `${n.toFixed(digits)}%` : n.toFixed(digits)
}

function fmtObjectiveValue(v) {
  const n = Number(v)
  if (Number.isNaN(n)) return v ?? '—'
  const obj = optResult.value?.objective || opt.objective
  if (obj === 'annual_return' || obj === 'max_drawdown') return `${n.toFixed(2)}%`
  return n.toFixed(4)
}

function fmtParams(params) {
  if (!params || typeof params !== 'object') return '—'
  return Object.entries(params)
    .map(([k, v]) => `${k}=${v}`)
    .join(', ')
}

onMounted(loadBaselines)
</script>

<template>
  <div class="space-y-6">
    <!-- 标题 -->
    <div>
      <h1 class="text-2xl font-bold text-white">参数优化与稳健性验证</h1>
      <p class="mt-1 text-sm text-slate-400">对策略参数做有界网格搜索与滚动样本外验证，检测过拟合</p>
    </div>

    <!-- 基准回测 -->
    <SectionCard title="基准回测" hint="选择一条已完成回测作为参数优化的基线">
      <div v-if="baselineLoading" class="text-sm text-slate-400">加载中…</div>
      <EmptyState v-else-if="!baselines.length" text="暂无成功回测，请先运行单次回测" />
      <label v-else class="block max-w-md">
        <span class="mb-1 block text-xs text-slate-400">基线</span>
        <select
          v-model="baselineRunId"
          class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40"
        >
          <option value="" disabled>请选择基线</option>
          <option v-for="b in baselines" :key="b.run_id" :value="b.run_id">{{ b.display_label }}</option>
        </select>
      </label>
    </SectionCard>

    <!-- 参数优化 -->
    <SectionCard title="参数优化" hint="对有界参数网格做批量回测，按目标指标排序并标记是否满足回撤约束">
      <div class="grid gap-4 md:grid-cols-2">
        <label class="block">
          <span class="mb-1 block text-xs text-slate-400">参数名 1</span>
          <input v-model="opt.param1Name" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
        </label>
        <label class="block">
          <span class="mb-1 block text-xs text-slate-400">候选值 1</span>
          <input v-model="opt.param1Values" placeholder="10,20,30" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
        </label>
        <label class="block">
          <span class="mb-1 block text-xs text-slate-400">参数名 2</span>
          <input v-model="opt.param2Name" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
        </label>
        <label class="block">
          <span class="mb-1 block text-xs text-slate-400">候选值 2</span>
          <input v-model="opt.param2Values" placeholder="0.0,0.05" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
        </label>
      </div>
      <p class="mt-2 text-xs text-slate-500">候选值以英文或中文逗号分隔，例如 10,20,30 或 0.0，0.05。</p>

      <div class="mt-4 grid gap-4 md:grid-cols-3">
        <label class="block">
          <span class="mb-1 block text-xs text-slate-400">排序指标</span>
          <select v-model="opt.objective" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40">
            <option v-for="o in objectiveOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </label>
        <label class="block">
          <span class="mb-1 block text-xs text-slate-400">最大回撤约束</span>
          <input v-model="opt.maxDrawdownLimit" type="number" min="0" step="0.01" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
        </label>
        <div class="flex items-end">
          <button @click="onOptimize" :disabled="opt.running" class="w-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70">
            {{ opt.running ? '优化中…' : '开始参数优化' }}
          </button>
        </div>
      </div>

      <p v-if="optError" class="mt-4 text-sm text-rose-300">{{ optError }}</p>

      <div v-if="optResult" class="mt-6 space-y-5">
        <p class="rounded-xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-xs leading-relaxed text-amber-200">
          演示数据：以下结果由随机数生成，仅用于界面预览，不是真实回测。接入真实优化引擎前，请勿据此评估策略。
        </p>
        <div class="grid gap-5 sm:grid-cols-2">
          <MetricCard label="组合数" :value="optResult.combination_count" sub="参数网格候选组合" />
          <MetricCard label="合格数" :value="optEligibleCount" sub="满足回撤约束" up :tone="optEligibleCount ? 'text-emerald-300' : 'text-slate-300'" />
        </div>
        <DataTable :columns="optColumns" :rows="optResult.results || []" empty="暂无优化结果">
          <template #cell-eligible="{ row }">
            <span :class="row.eligible ? 'text-emerald-300' : 'text-rose-300'">{{ row.eligible ? '合格' : '不合格' }}</span>
          </template>
          <template #cell-objective_value="{ row }">{{ fmtObjectiveValue(row.objective_value) }}</template>
          <template #cell-max_drawdown="{ row }">
            <span class="text-rose-300">{{ fmtNum(row.max_drawdown, true) }}</span>
          </template>
          <template #cell-parameters="{ row }">
            <span class="font-mono text-xs text-slate-400">{{ fmtParams(row.parameters) }}</span>
          </template>
          <template #cell-status="{ row }">
            <StatusPill :value="row.status" />
          </template>
        </DataTable>
      </div>
    </SectionCard>

    <!-- 滚动样本外验证 -->
    <SectionCard title="滚动样本外验证" hint="在滚动时间窗上训练与测试，评估参数在样本外的稳定性">
      <div class="grid gap-4 md:grid-cols-5">
        <label class="block">
          <span class="mb-1 block text-xs text-slate-400">训练期（月）</span>
          <input v-model="wf.trainingMonths" type="number" min="1" step="1" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
        </label>
        <label class="block">
          <span class="mb-1 block text-xs text-slate-400">测试期（月）</span>
          <input v-model="wf.testMonths" type="number" min="1" step="1" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
        </label>
        <label class="block">
          <span class="mb-1 block text-xs text-slate-400">步长（月）</span>
          <input v-model="wf.stepMonths" type="number" min="1" step="1" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
        </label>
        <label class="block">
          <span class="mb-1 block text-xs text-slate-400">最多窗口</span>
          <input v-model="wf.maxWindows" type="number" min="1" step="1" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
        </label>
        <label class="block">
          <span class="mb-1 block text-xs text-slate-400">排序指标</span>
          <select v-model="wf.objective" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40">
            <option v-for="o in objectiveOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </label>
      </div>
      <div class="mt-4">
        <button @click="onWalkForward" :disabled="wf.running" class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70">
          {{ wf.running ? '验证中…' : '开始滚动验证' }}
        </button>
      </div>

      <p v-if="wfError" class="mt-4 text-sm text-rose-300">{{ wfError }}</p>

      <div v-if="wfResult" class="mt-6 space-y-5">
        <p class="rounded-xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-xs leading-relaxed text-amber-200">
          演示数据：以下窗口结果由随机数生成，仅用于界面预览，不是真实回测。接入真实验证引擎前，请勿据此评估策略。
        </p>
        <div class="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="成功窗口" :value="wfResult.summary.successful_windows" sub="共 {{ wfResult.window_count }} 个窗口" />
          <MetricCard
            label="样本外累计收益"
            :value="fmtNum(wfResult.summary.out_of_sample_cumulative_return, true)"
            :up="toNum(wfResult.summary.out_of_sample_cumulative_return) >= 0"
            :tone="toNum(wfResult.summary.out_of_sample_cumulative_return) >= 0 ? 'text-emerald-300' : 'text-rose-300'"
          />
          <MetricCard label="正收益窗口比例" :value="fmtNum(wfResult.summary.positive_window_ratio, true)" up tone="text-emerald-300" />
          <MetricCard label="最差窗口回撤" :value="fmtNum(wfResult.summary.worst_window_drawdown, true)" :up="false" tone="text-rose-300" />
        </div>

        <div v-if="wfResult.summary.trust_warning" class="rounded-xl border border-amber-400/30 bg-amber-400/10 p-4 text-sm text-amber-200">
          {{ wfResult.summary.trust_warning }}
        </div>

        <DataTable :columns="wfColumns" :rows="wfRows" empty="暂无滚动窗口结果">
          <template #cell-test_cumulative_return="{ row }">
            <span :class="toNum(row.test_cumulative_return) >= 0 ? 'text-emerald-300' : 'text-rose-300'">{{ fmtNum(row.test_cumulative_return, true) }}</span>
          </template>
          <template #cell-test_max_drawdown="{ row }">
            <span class="text-rose-300">{{ fmtNum(row.test_max_drawdown, true) }}</span>
          </template>
          <template #cell-status="{ row }">
            <StatusPill :value="row.status" />
          </template>
        </DataTable>
      </div>
    </SectionCard>
  </div>
</template>
