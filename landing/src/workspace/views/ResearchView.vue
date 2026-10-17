<script setup>
import { computed, onActivated, reactive, ref, watch } from 'vue'
import { openResearch } from '../researchNavigation.js'
import { researchBaselines, runOptimization, runWalkForward } from '../../api.js'
import { candidateGrid, candidateLabel, combinationCount, parameterHint } from '../researchGrid.js'
import DataTable from '../ui/DataTable.vue'
import EmptyState from '../ui/EmptyState.vue'
import MetricCard from '../ui/MetricCard.vue'
import SectionCard from '../ui/SectionCard.vue'
import StatusPill from '../ui/StatusPill.vue'

const props = defineProps({
  routeContext: { type: Object, default: () => ({}) },
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
const limits = ref({ combinations: 24, backtests: 100 })
const baseline = computed(() => baselines.value.find((b) => b.run_id === baselineRunId.value) || null)
const parameters = computed(() => baseline.value?.parameters || [])

async function loadBaselines() {
  baselineLoading.value = true
  try {
    const data = await researchBaselines()
    baselines.value = data.items || []
    limits.value = { combinations: data.max_combinations || 24, backtests: data.max_backtests || 100 }
    if (props.routeContext.baseline) {
      baselineRunId.value = baselines.value.some((b) => b.run_id === props.routeContext.baseline) ? props.routeContext.baseline : ''
    }
    if (baselines.value.length && !baselines.value.some((b) => b.run_id === baselineRunId.value)) {
      baselineRunId.value = baselines.value[0].run_id
    }
  } catch (e) {
    props.notify(e.message || '加载基线失败')
  } finally {
    baselineLoading.value = false
  }
}

// ---------- 候选参数：只能从基准策略真实存在的参数里选 ----------
const slots = reactive([{ name: '', values: '' }, { name: '', values: '' }])
function resetSlots() {
  slots.forEach((slot, index) => {
    const parameter = parameters.value[index]
    slot.name = parameter?.name || ''
    slot.values = parameter ? String(parameter.current) : ''
  })
}
function onSlotName(slot) {
  const parameter = parameters.value.find((p) => p.name === slot.name)
  slot.values = parameter ? String(parameter.current) : ''
}
const grid = computed(() => candidateGrid(slots))
const combinations = computed(() => combinationCount(grid.value))
const gridProblem = computed(() => {
  if (!parameters.value.length) return ''
  if (slots[0].name && slots[0].name === slots[1].name) return '两行选择了同一个参数，请改成不同的参数。'
  if (!combinations.value) return '请至少为一个参数填写候选值。'
  if (combinations.value > limits.value.combinations) return `候选值共有 ${combinations.value} 种组合，超过上限 ${limits.value.combinations} 种，请减少候选值。`
  return ''
})

// ---------- 参数优化 ----------
const opt = reactive({ objective: 'sharpe', maxDrawdownLimit: 0.3, running: false })
const optResult = ref(null)
const optError = ref('')

async function onOptimize() {
  if (!baselineRunId.value) return props.notify('请先选择基准回测')
  if (gridProblem.value) return props.notify(gridProblem.value)
  opt.running = true
  optError.value = ''
  optResult.value = null
  try {
    optResult.value = await runOptimization({
      baseline_run_id: baselineRunId.value,
      parameter_grid: grid.value,
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
  { key: 'parameters', label: '参数' },
  { key: 'objective_value', label: '目标值', align: 'right' },
  { key: 'sharpe', label: '夏普', align: 'right' },
  { key: 'cumulative_return', label: '累计收益', align: 'right' },
  { key: 'max_drawdown', label: '最大回撤', align: 'right' },
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
  maxWindows: 4,
  running: false,
})
const wfResult = ref(null)
const wfError = ref('')
const wfBacktests = computed(() => (Number(wf.maxWindows) || 0) * (combinations.value + 1))

async function onWalkForward() {
  if (!baselineRunId.value) return props.notify('请先选择基准回测')
  if (gridProblem.value) return props.notify(gridProblem.value)
  wf.running = true
  wfError.value = ''
  wfResult.value = null
  try {
    wfResult.value = await runWalkForward({
      baseline_run_id: baselineRunId.value,
      parameter_grid: grid.value,
      objective: wf.objective,
      training_months: Number(wf.trainingMonths) || 12,
      test_months: Number(wf.testMonths) || 3,
      step_months: Number(wf.stepMonths) || 3,
      max_windows: Number(wf.maxWindows) || 4,
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
  { key: 'selected_parameters', label: '训练期选出的参数' },
  { key: 'test_cumulative_return', label: '样本外收益', align: 'right' },
  { key: 'test_max_drawdown', label: '回撤', align: 'right' },
  { key: 'test_sharpe', label: '夏普', align: 'right' },
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
  if (v === null || v === undefined) return '—'
  const n = Number(v)
  if (Number.isNaN(n)) return v
  const obj = optResult.value?.objective || opt.objective
  if (obj === 'annual_return' || obj === 'max_drawdown') return `${n.toFixed(2)}%`
  return n.toFixed(4)
}

function fmtParams(params) {
  const entries = Object.entries(params || {})
  if (!entries.length) return '—'
  return entries
    .map(([k, v]) => {
      const parameter = parameters.value.find((p) => p.name === k)
      return `${parameter?.label || k}=${candidateLabel(parameter, v)}`
    })
    .join('，')
}

watch(() => props.routeContext.baseline, (value) => {
  if (value) baselineRunId.value = baselines.value.some((b) => b.run_id === value) ? value : ''
})
// 换了基准策略，可调参数也不同：重置候选值，并清掉上一个基准的结果。
watch(baseline, () => {
  resetSlots()
  optResult.value = null
  wfResult.value = null
})
onActivated(loadBaselines)
</script>

<template>
  <div class="space-y-6">
    <!-- 标题 -->
    <div class="glass glass-sheen rounded-2xl p-6">
      <h1 class="text-xl font-bold text-white">参数验证</h1>
      <p class="mt-2 text-sm text-slate-400">先用参数优化比较不同取值，再用样本外验证检查：换一段时间，结论是否仍然成立。每一组候选参数都会运行一次真实回测；除候选参数外，股票池、资金、风控等配置都与基准回测相同。</p>
    </div>

    <!-- 基准回测 -->
    <SectionCard title="基准回测" hint="选择一条已完成的回测，下面两种验证都以它的配置为基础">
      <div v-if="baselineLoading" class="text-sm text-slate-400">加载中…</div>
      <div v-else-if="!baselines.length"><EmptyState text="暂无成功回测，请先运行策略回测" /><button class="mt-3 text-sm text-indigo-300" @click="openResearch('backtest-review')">去配置回测 →</button></div>
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

    <!-- 候选参数 -->
    <SectionCard title="候选参数" hint="可以比较策略自己的参数，也可以比较持股数量和调仓频率；下面两种验证共用这里的配置">
      <p v-if="baseline && !parameters.length" class="text-sm text-amber-200">这条回测使用的策略已删除或无法加载，不能做参数验证。请换一条基准回测。</p>
      <template v-else-if="baseline">
        <div v-for="(slot, index) in slots" :key="index" class="grid gap-4 md:grid-cols-2" :class="{ 'mt-4': index }">
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">参数 {{ index + 1 }}</span>
            <select v-model="slot.name" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" @change="onSlotName(slot)">
              <option value="" class="bg-ink">不使用</option>
              <option v-for="p in parameters" :key="p.name" :value="p.name" class="bg-ink">{{ p.label }}（{{ p.name }}）</option>
            </select>
          </label>
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">候选值 {{ index + 1 }}</span>
            <input v-model="slot.values" :disabled="!slot.name" placeholder="例如 10,20,30" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40 disabled:opacity-50" />
            <span v-if="slot.name" class="mt-1 block text-xs text-slate-500">{{ parameterHint(parameters.find((p) => p.name === slot.name)) }}</span>
          </label>
        </div>
        <p class="mt-3 text-xs text-slate-500">候选值以英文或中文逗号分隔。当前共 {{ combinations }} 种组合，最多 {{ limits.combinations }} 种。</p>
        <p v-if="gridProblem" class="mt-2 text-sm text-amber-200" role="alert">{{ gridProblem }}</p>
      </template>
    </SectionCard>

    <SectionCard title="第一步：参数优化" hint="在基准回测的区间内，按目标指标比较候选组合，并检查回撤约束">
      <div class="mt-4 grid gap-4 md:grid-cols-3">
        <label class="block">
          <span class="mb-1 block text-xs text-slate-400">排序指标</span>
          <select v-model="opt.objective" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40">
            <option v-for="o in objectiveOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </label>
        <label class="block">
          <span class="mb-1 block text-xs text-slate-400">最大回撤约束（0.3 表示 30%，填 0 表示不限制）</span>
          <input v-model="opt.maxDrawdownLimit" type="number" min="0" max="1" step="0.01" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
        </label>
        <div class="flex items-end">
          <button @click="onOptimize" :disabled="opt.running || !baselineRunId || !parameters.length || !!gridProblem" class="w-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70">
            {{ opt.running ? '优化中…' : `开始参数优化（${combinations} 次回测）` }}
          </button>
        </div>
      </div>

      <p v-if="opt.running" class="mt-4 text-sm text-slate-400" role="status">正在运行 {{ combinations }} 次真实回测，可能需要几十秒到几分钟，请保持页面打开。</p>
      <p v-if="optError" class="mt-4 text-sm text-rose-300" role="alert">{{ optError }}</p>

      <div v-if="optResult" class="mt-6 space-y-5">
        <p class="text-xs text-slate-400">回测区间 {{ optResult.start_date }} ~ {{ optResult.end_date }}，与基准回测相同。以下每一行都是一次真实回测的结果。</p>
        <div class="grid gap-5 sm:grid-cols-2">
          <MetricCard label="组合数" :value="optResult.combination_count" sub="每个组合运行一次回测" />
          <MetricCard label="合格数" :value="optEligibleCount" sub="回测成功、指标可信并满足回撤约束" up :tone="optEligibleCount ? 'text-emerald-300' : 'text-slate-300'" />
        </div>
        <p v-if="optResult.selection_bias?.message" class="rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm leading-relaxed text-amber-200">
          选择偏差提示：{{ optResult.selection_bias.message }}
        </p>
        <DataTable :columns="optColumns" :rows="optResult.results || []" empty="暂无优化结果">
          <template #cell-rank="{ row }">{{ row.rank ?? '—' }}</template>
          <template #cell-eligible="{ row }">
            <span :class="row.eligible ? 'text-emerald-300' : 'text-rose-300'">{{ row.eligible ? '合格' : '不合格' }}</span>
          </template>
          <template #cell-objective_value="{ row }">{{ fmtObjectiveValue(row.objective_value) }}</template>
          <template #cell-sharpe="{ row }">{{ fmtNum(row.sharpe) }}</template>
          <template #cell-cumulative_return="{ row }">{{ fmtNum(row.cumulative_return, true) }}</template>
          <template #cell-max_drawdown="{ row }">
            <span class="text-rose-300">{{ fmtNum(row.max_drawdown, true) }}</span>
          </template>
          <template #cell-parameters="{ row }">
            <span class="text-xs text-slate-400">{{ fmtParams(row.parameters) }}</span>
          </template>
          <template #cell-status="{ row }">
            <StatusPill :value="row.status" />
            <span v-if="row.error" class="mt-1 block max-w-xs text-xs text-rose-300">{{ row.error }}</span>
          </template>
        </DataTable>
      </div>
    </SectionCard>

    <!-- 滚动样本外验证 -->
    <SectionCard title="第二步：样本外验证" hint="滚动进行：每个窗口先在训练期选出最好的参数，再放到之后没用过的测试期回测">
      <div class="grid gap-4 md:grid-cols-5">
        <label class="block">
          <span class="mb-1 block text-xs text-slate-400">训练期（月）</span>
          <input v-model="wf.trainingMonths" type="number" min="3" step="1" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
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
      <p class="mt-3 text-xs text-slate-500">使用本地最近的一段行情，不限于基准回测的区间。最多运行 {{ wfBacktests }} 次回测（上限 {{ limits.backtests }} 次）。</p>
      <div class="mt-4">
        <button @click="onWalkForward" :disabled="wf.running || !baselineRunId || !parameters.length || !!gridProblem" class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70">
          {{ wf.running ? '验证中…' : '开始滚动验证' }}
        </button>
      </div>

      <p v-if="wf.running" class="mt-4 text-sm text-slate-400" role="status">正在运行真实回测，可能需要几分钟，请保持页面打开。</p>
      <p v-if="wfError" class="mt-4 text-sm text-rose-300" role="alert">{{ wfError }}</p>

      <div v-if="wfResult" class="mt-6 space-y-5">
        <p class="text-xs text-slate-400">使用行情 {{ wfResult.start_date }} ~ {{ wfResult.end_date }}，共运行 {{ wfResult.backtest_count }} 次真实回测。每个窗口先在训练区间选出最好的参数，再用它在之后的测试区间回测。</p>
        <div class="grid gap-5 sm:grid-cols-2 xl:grid-cols-5">
          <MetricCard label="成功窗口" :value="wfResult.summary.successful_windows" :sub="`共 ${wfResult.window_count} 个窗口`" />
          <MetricCard
            label="样本外累计收益"
            :value="fmtNum(wfResult.summary.out_of_sample_cumulative_return, true)"
            :up="toNum(wfResult.summary.out_of_sample_cumulative_return) >= 0"
            :tone="toNum(wfResult.summary.out_of_sample_cumulative_return) >= 0 ? 'text-emerald-300' : 'text-rose-300'"
          />
          <MetricCard label="正收益窗口比例" :value="fmtNum(wfResult.summary.positive_window_ratio, true)" up tone="text-emerald-300" />
          <MetricCard label="最差窗口回撤" :value="fmtNum(wfResult.summary.worst_window_drawdown, true)" :up="false" tone="text-rose-300" />
          <MetricCard label="窗口平均夏普" :value="fmtNum(wfResult.summary.average_window_sharpe)" />
        </div>

        <div v-if="wfResult.summary.trust_warning" class="rounded-xl border border-amber-400/30 bg-amber-400/10 p-4 text-sm text-amber-200">
          {{ wfResult.summary.trust_warning }}
        </div>

        <DataTable :columns="wfColumns" :rows="wfRows" empty="暂无滚动窗口结果">
          <template #cell-selected_parameters="{ row }">
            <span class="text-xs text-slate-400">{{ fmtParams(row.selected_parameters) }}</span>
          </template>
          <template #cell-test_cumulative_return="{ row }">
            <span :class="toNum(row.test_cumulative_return) >= 0 ? 'text-emerald-300' : 'text-rose-300'">{{ fmtNum(row.test_cumulative_return, true) }}</span>
          </template>
          <template #cell-test_max_drawdown="{ row }">
            <span class="text-rose-300">{{ fmtNum(row.test_max_drawdown, true) }}</span>
          </template>
          <template #cell-test_sharpe="{ row }">{{ fmtNum(row.test_sharpe) }}</template>
          <template #cell-status="{ row }">
            <StatusPill :value="row.status" />
            <span v-if="row.error" class="mt-1 block max-w-xs text-xs text-rose-300">{{ row.error }}</span>
          </template>
        </DataTable>
      </div>
    </SectionCard>
  </div>
</template>
