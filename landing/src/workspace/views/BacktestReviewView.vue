<script setup>
import { computed, onActivated, reactive, ref, watch } from 'vue'
import { getBacktestBenchmark, getBacktestCatalog, getBacktest, getRunAudit, listPackages, submitBacktest } from '../../api.js'
import { openResearch } from '../researchNavigation.js'
import { backtestId, runTime, strategyName, validityLabel } from '../runRecords.js'
import BacktestAiReview from '../ui/BacktestAiReview.vue'
import RiskSettings from '../ui/RiskSettings.vue'
import MetricCard from '../ui/MetricCard.vue'
import SectionCard from '../ui/SectionCard.vue'
import LineChart from '../ui/LineChart.vue'
import EmptyState from '../ui/EmptyState.vue'
import FormField from '../ui/FormField.vue'
import DataTable from '../ui/DataTable.vue'
import StatusPill from '../ui/StatusPill.vue'
import { pendingAuditRun } from '../auditLink.js'
import { benchmarkCards, benchmarkChoices, benchmarkNote, benchmarkSeries } from '../benchmarkPresentation.js'
import { CURRENT_POOL, marketChoices, marketLabel, marketNote, usableMarket } from '../marketPresentation.js'

const props = defineProps({
  routeContext: { type: Object, default: () => ({}) },
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

// ---------- 新建回测表单 ----------
// 股票范围：自己的股票池，或某个指数当时的成分股（来自回测目录接口）。
const markets = ref([])
const marketOptions = computed(() => marketChoices(markets.value))
const marketHint = computed(() => marketNote(form.market, markets.value))
const strategyOptions = ref([])
const catalogLoading = ref(false)
const catalogErrors = ref([])
const strategyParameters = reactive({})
const selectedStrategy = computed(() => strategyOptions.value.find((s) => s.value === form.strategy))
const riskEditor = ref(null)
const riskOpen = ref(false)
function chooseStrategy() {
  const strategy = selectedStrategy.value
  for (const key of Object.keys(strategyParameters)) delete strategyParameters[key]
  Object.assign(strategyParameters, strategy?.defaults || {})
  if (strategy?.top_n) form.max_positions = strategy.top_n
  if (strategy?.rebalance) form.rebalance = strategy.rebalance
}
const rebalances = [
  { value: 'daily', label: '每日' },
  { value: 'weekly', label: '每周' },
  { value: 'monthly', label: '每月' },
]

const form = reactive({
  strategy: '',
  market: CURRENT_POOL,
  from_date: '2025-01-01',
  to_date: '2025-12-31',
  initial_capital: 1000000,
  max_positions: 10,
  rebalance: 'weekly',
})

const running = ref(false)
const runError = ref('')

// ---------- 回测结果 ----------
// 这里只显示一次回测：刚运行的，或从研究记录打开的。以前的回测都在研究记录里。
const selectedId = ref(null)
const current = ref(null)
const detailLoading = ref(false)

const result = computed(() => current.value?.result || {})
const shownStrategy = computed(() => {
  const config = result.value.effective_config || {}
  return strategyName(strategyOptions.value, config.strategy_reference || config.strategy_plugin, current.value?.strategy)
})

// ---------- 可信度审计（结果的属性，随详情一起加载） ----------
const audit = ref(null)
// 评级视觉语言与审计页一致：A 绿 / B 蓝 / C 黄 / D 红
const GRADE_TONE = { A: 'text-emerald-300', B: 'text-sky-300', C: 'text-amber-300', D: 'text-rose-300' }
const gradeTone = computed(() => GRADE_TONE[audit.value?.grade] || 'text-slate-300')
const gradeValue = computed(() => audit.value?.grade || '待检查')
const gradeSub = computed(() =>
  audit.value?.headline ? '点击下方按钮查看证据链' : '含数据、成本与参数搜索偏差等审计维度，不代表未来盈利概率'
)

function openAudit() {
  if (selectedId.value === null || selectedId.value === '') return
  pendingAuditRun.value = `run-${selectedId.value}`
  openResearch('audit-report', { run: selectedId.value })
}

const tabs = ['概览', '交易与成本', '持仓分析']
const activeTab = ref('概览')

// ---------- 格式化辅助 ----------
const num = (v) => {
  if (v === null || v === undefined || v === '') return null
  const n = Number(v)
  return Number.isNaN(n) ? null : n
}
const fmtPct = (v) => (num(v) === null ? '—' : `${Number(v).toFixed(2)}%`)
const fmtNum = (v) => (num(v) === null ? '—' : Number(v).toFixed(2))
const fmtMoney = (v) =>
  num(v) === null ? '—' : `¥${Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`

const finalEquity = computed(() => {
  const fe = num(result.value.final_equity)
  if (fe !== null) return fe
  const eq = result.value.equity
  if (Array.isArray(eq) && eq.length) return num(eq[eq.length - 1])
  return null
})

const totalCost = computed(() => {
  const r = result.value
  return num(r.total_cost ?? r.trading_cost ?? r.total_trading_cost ?? r.cost)
})

// 累计收益、最大回撤已在概览顶部，总交易成本在“交易与成本”里，这里不重复。
const metrics = computed(() => {
  const annual = num(result.value.annual_return)
  return [
    { label: '最终权益', value: fmtMoney(finalEquity.value), tone: '' },
    { label: '年化收益', value: fmtPct(annual), tone: annual === null ? '' : annual >= 0 ? 'text-emerald-300' : 'text-rose-300' },
    { label: '夏普比率', value: fmtNum(result.value.sharpe), tone: '' },
    { label: '索提诺比率', value: fmtNum(result.value.sortino), tone: '' },
    { label: '卡玛比率', value: fmtNum(result.value.calmar), tone: '' },
  ]
})

// 和基准的对比。默认是回测时记录的基准（沪深 300），可以换成本地有行情的其他常用指数；
// 换过一次后记住这个选择。回测没有记录基准时为空。
const BENCHMARK_KEY = 'fq-benchmark'
const benchmark = ref(null)
const benchmarkLoading = ref(false)
const benchmarkOptions = computed(() => benchmarkChoices(current.value?.benchmark_options, benchmark.value))
function rememberedBenchmark() {
  try { return localStorage.getItem(BENCHMARK_KEY) || '' } catch { return '' }
}
async function chooseBenchmark(symbol, remember = true, control = null) {
  const id = selectedId.value
  benchmarkLoading.value = true
  try {
    const next = await getBacktestBenchmark(id, symbol)
    if (id !== selectedId.value) return
    // 自动沿用上次的选择时，只有能比较才换；否则留在回测记录的基准上。
    if (!remember && !next.comparable) return
    benchmark.value = next
    if (remember) { try { localStorage.setItem(BENCHMARK_KEY, symbol) } catch { /* 记不住也不影响比较 */ } }
  } catch (e) {
    if (remember) props.notify(e.message || '读取基准对比失败')
    // 没换成：下拉框回到正在显示的那个指数。
    if (control && benchmark.value) control.value = benchmark.value.symbol
  } finally {
    benchmarkLoading.value = false
  }
}
const comparisonCards = computed(() => benchmarkCards(benchmark.value))
const comparisonSeries = computed(() => benchmarkSeries(benchmark.value))
const comparisonNote = computed(() => benchmarkNote(benchmark.value))

const equitySeries = computed(() => [
  { label: '资金曲线', color: '#818cf8', points: Array.isArray(result.value.equity) ? result.value.equity : [] },
])

// 交易与成本 / 持仓分析
const tradeCols = [
  { key: 'date', label: '时间' },
  { key: 'symbol', label: '标的' },
  { key: 'side', label: '方向' },
  { key: 'quantity', label: '数量', align: 'right' },
  { key: 'price', label: '价格', align: 'right' },
  { key: 'amount', label: '金额', align: 'right' },
  { key: 'fee', label: '手续费', align: 'right' },
]
const positionCols = [
  { key: 'symbol', label: '标的' },
  { key: 'name', label: '名称' },
  { key: 'quantity', label: '数量', align: 'right' },
  { key: 'avg_price', label: '持仓均价', align: 'right' },
  { key: 'price', label: '现价', align: 'right' },
  { key: 'market_value', label: '市值', align: 'right' },
  { key: 'pnl', label: '盈亏', align: 'right' },
]

// ---------- 逻辑 ----------
async function loadDetail() {
  if (selectedId.value === null || selectedId.value === '') return
  detailLoading.value = true
  current.value = null
  benchmark.value = null
  audit.value = null
  try {
    current.value = await getBacktest(selectedId.value)
    benchmark.value = current.value.benchmark || null
    const preferred = rememberedBenchmark()
    if (benchmark.value && preferred !== benchmark.value.symbol && (current.value.benchmark_options || []).some((item) => item.symbol === preferred)) {
      chooseBenchmark(preferred, false)
    }
    if (props.routeContext.mode === 'reuse') {
      const config = current.value.result?.effective_config
      const reference = config?.strategy_reference || config?.strategy_plugin
      if (reference && strategyOptions.value.some((s) => s.value === reference)) {
        form.strategy = reference
        chooseStrategy()
        for (const key of ['from_date', 'to_date', 'initial_capital', 'max_positions', 'rebalance']) {
          if (config[key] != null) form[key] = config[key]
        }
        form.market = usableMarket(config.market, markets.value)
        if (!reference.startsWith('package:')) Object.assign(strategyParameters, config.strategy_parameters || {})
      }
    }
    audit.value = null
    // 评级随详情加载；明细缺失或审计失败时显示"待检查"，不阻塞结果展示。
    try {
      audit.value = await getRunAudit(`run-${selectedId.value}`)
    } catch {
      audit.value = null
    }
  } catch (e) {
    props.notify(e.message || '加载回测详情失败')
  } finally {
    detailLoading.value = false
  }
}

async function onSubmit() {
  if (!selectedStrategy.value) return props.notify('请选择可执行策略')
  if (!riskEditor.value?.ready) return props.notify('风控配置尚未加载，请稍后或重试')
  if (riskEditor.value?.dirty) { riskOpen.value = true; return props.notify('请先保存修改的风控配置') }
  if (form.from_date >= form.to_date) return props.notify('开始日期需早于结束日期')
  running.value = true
  runError.value = ''
  try {
    const data = await submitBacktest({
      strategy: form.strategy.trim(),
      market: form.market,
      from_date: form.from_date,
      to_date: form.to_date,
      initial_capital: Number(form.initial_capital),
      max_positions: Number(form.max_positions),
      rebalance: form.rebalance,
      strategy_parameters: { ...strategyParameters },
    })
    props.notify('回测已完成')
    activeTab.value = '概览'
    // 把这次回测写进链接：刷新或后退仍然是这次结果，结果由下面对链接的监听加载。
    openResearch('backtest-review', { run: data.id })
  } catch (e) {
    runError.value = e.message || '回测失败'
    props.notify(e.message || '回测失败')
  } finally {
    running.value = false
  }
}

async function loadCatalog() {
  catalogLoading.value = true
  catalogErrors.value = []
  try {
    const [catalog, packages] = await Promise.all([getBacktestCatalog(), listPackages()])
    strategyOptions.value = [
      ...(packages.items || []).map((p) => ({ value: `package:${p.package_id}`, label: `${p.name} · 规则策略`, top_n: p.top_n, rebalance: p.rebalance })),
      ...catalog.items,
    ]
    markets.value = catalog.markets || []
    form.market = usableMarket(form.market, markets.value)
    const requested = props.routeContext.strategy
    if (requested) {
      form.strategy = strategyOptions.value.some((s) => s.value === requested) ? requested : ''
      if (!form.strategy) catalogErrors.value.unshift('选中的策略已删除或无法加载，请重新选择。')
      chooseStrategy()
    } else if (!strategyOptions.value.some((s) => s.value === form.strategy)) {
      form.strategy = catalog.default
      chooseStrategy()
    }
  } catch (e) { catalogErrors.value = [e.message || '加载策略目录失败']; strategyOptions.value = []; form.strategy = '' }
  finally { catalogLoading.value = false }
}
async function loadRouteRun() {
  const id = backtestId(props.routeContext.run)
  if (id === null) {
    selectedId.value = null
    current.value = null
    benchmark.value = null
    audit.value = null
    return
  }
  if (id === selectedId.value && current.value && props.routeContext.mode !== 'reuse') return
  selectedId.value = id
  await loadDetail()
}
watch(() => props.routeContext.strategy, (value) => {
  if (!value || catalogLoading.value) return
  form.strategy = strategyOptions.value.some((s) => s.value === value) ? value : ''
  chooseStrategy()
})
watch(() => props.routeContext.run, loadRouteRun)
onActivated(async () => {
  await loadCatalog()
  await loadRouteRun()
})
</script>

<template>
  <div class="space-y-6">
    <!-- 标题 -->
    <div class="glass glass-sheen rounded-2xl p-6">
      <h1 class="text-xl font-bold text-white">策略回测</h1>
      <p class="mt-2 text-sm text-slate-400">选择策略，设置日期、资金和风控，确认后再运行。</p>
      <button class="mt-3 text-sm text-indigo-300" @click="openResearch('strategy-hub')">← 返回我的策略</button>
    </div>

    <!-- 新建回测 -->
    <SectionCard title="新建回测" hint="配置策略与市场区间，运行一次确定性回测">
      <p v-if="routeContext.mode === 'reuse'" class="mb-4 text-sm text-slate-400">已带入历史区间、资金、股票范围与策略参数；风控使用当前设置。</p>
      <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <FormField label="策略" type="select" v-model="form.strategy" :options="[{ value: '', label: catalogLoading ? '加载中…' : '请选择策略' }, ...strategyOptions]" :disabled="catalogLoading" @update:model-value="chooseStrategy" />
        <FormField label="股票范围" type="select" v-model="form.market" :options="marketOptions" />
        <FormField label="开始日期" type="date" v-model="form.from_date" />
        <FormField label="结束日期" type="date" v-model="form.to_date" />
        <FormField label="初始资金" type="number" v-model="form.initial_capital" :min="0" :step="10000" />
        <FormField label="最大持仓" type="number" v-model="form.max_positions" :min="1" :max="form.strategy.startsWith('package:') ? 50 : 500" :step="1" />
        <FormField label="调仓频率" type="select" v-model="form.rebalance" :options="rebalances" />
      </div>
      <p v-if="marketHint" class="mt-3 text-xs text-slate-400">{{ marketHint }}</p>
      <p v-for="(error, i) in catalogErrors" :key="i" role="alert" class="mt-3 text-sm text-amber-300">{{ error }}</p>
      <div v-if="selectedStrategy?.parameters?.length" class="mt-5 grid gap-4 border-t border-white/10 pt-5 md:grid-cols-2 xl:grid-cols-4">
        <FormField v-for="p in selectedStrategy.parameters" :key="p.name" v-model="strategyParameters[p.name]" :label="p.label" :type="p.choices?.length ? 'select' : p.kind === 'boolean' ? 'checkbox' : ['integer', 'number'].includes(p.kind) ? 'number' : 'text'" :options="(p.choices || []).map((v) => ({ value: v, label: v }))" :min="p.minimum" :max="p.maximum" :step="p.kind === 'integer' ? 1 : 'any'" :hint="p.description" />
      </div>
      <details :open="riskOpen" class="mt-5 rounded-xl border border-white/10 bg-white/5" @toggle="riskOpen = $event.target.open">
        <summary class="cursor-pointer px-4 py-3 text-sm text-slate-300">风险设置 <span v-if="riskEditor?.dirty" class="text-amber-300">· 有未保存修改</span></summary>
        <div class="p-3 pt-0"><RiskSettings ref="riskEditor" :notify="notify" /></div>
      </details>
      <p v-if="runError" class="mt-4 text-sm text-rose-300">{{ runError }}</p>
      <div class="mt-5 flex justify-end">
        <button
          @click="onSubmit"
          :disabled="running || catalogLoading || !selectedStrategy || !riskEditor?.ready"
          class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-6 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
        >
          {{ running ? '回测中…' : '运行回测' }}
        </button>
      </div>
    </SectionCard>

    <!-- 回测结果 -->
    <SectionCard title="回测结果" hint="一次回测的收益、风险、交易成本与持仓">
      <template #actions>
        <button class="text-sm text-indigo-300 hover:text-indigo-200" @click="openResearch('run-library')">查看以前的回测 →</button>
      </template>

      <div v-if="detailLoading && !current" class="text-sm text-slate-400">加载中…</div>

      <EmptyState v-else-if="!current" text="运行回测后，结果显示在这里。以前的回测可以在「研究记录」里重新打开。" />

      <div v-else class="space-y-4">
        <!-- 元信息 -->
        <div class="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm">
          <span class="text-slate-400">策略</span>
          <span class="font-medium text-white">{{ shownStrategy }}</span>
          <span class="text-slate-400">股票范围</span>
          <span class="text-white">{{ marketLabel(current.market, markets) }}</span>
          <span class="text-slate-400">区间</span>
          <span class="text-white">{{ current.from_date }} ~ {{ current.to_date }}</span>
          <span class="text-slate-400">运行时间</span>
          <span class="text-white">{{ runTime(current.created_at) }}</span>
          <StatusPill :value="current.status || '—'" />
        </div>

        <!-- 子 Tab -->
        <div class="flex w-fit rounded-full border border-white/10 bg-white/5 p-0.5 text-xs">
          <button
            v-for="t in tabs"
            :key="t"
            @click="activeTab = t"
            class="rounded-full px-3 py-1 transition"
            :class="activeTab === t ? 'bg-gradient-to-r from-indigo-500 to-violet-500 text-white' : 'text-slate-400 hover:text-slate-200'"
          >
            {{ t }}
          </button>
        </div>

        <div v-if="detailLoading" class="text-sm text-slate-400">加载中…</div>

        <div v-if="current" class="rounded-xl border border-amber-400/20 bg-white/5 p-4 text-xs text-slate-300">
          <p>数据状态：{{ validityLabel(result) }}；{{ result.metrics_reliable ? '指标可计算，请结合警告审阅' : '指标不可作为可信结论' }}</p>
          <p v-if="result.effective_config" class="mt-2">实际配置：{{ shownStrategy }} · ¥{{ Number(result.effective_config.initial_capital).toLocaleString() }} · 最多 {{ result.effective_config.max_positions }} 只 · {{ rebalances.find(r => r.value === result.effective_config.rebalance)?.label }}调仓 · {{ result.effective_config.from_date }} 至 {{ result.effective_config.to_date }}</p>
          <p v-for="(issue, index) in result.validity_issues || []" :key="index" class="mt-1 text-amber-300" :title="issue.code">{{ issue.message }}</p>
        </div>
        <!-- 概览 -->
        <div v-if="!detailLoading && activeTab === '概览'" class="space-y-4">
          <!-- 结论先行：收益 / 回撤 / 可信度评级 -->
          <section class="grid gap-5 sm:grid-cols-3">
            <MetricCard
              label="累计收益"
              :value="fmtPct(result.total_return)"
              :tone="num(result.total_return) === null ? '' : num(result.total_return) >= 0 ? 'text-emerald-300' : 'text-rose-300'"
            />
            <MetricCard label="最大回撤" :value="fmtPct(result.max_drawdown)" sub="资金曲线从峰值到谷底的最大跌幅" tone="text-rose-300" />
            <MetricCard label="可信度评级" :value="gradeValue" :sub="gradeSub" :tone="gradeTone" />
          </section>
          <section class="grid gap-5 sm:grid-cols-2 xl:grid-cols-5">
            <MetricCard v-for="m in metrics" :key="m.label" :label="m.label" :value="m.value" :tone="m.tone" />
          </section>
          <button
            @click="openAudit"
            class="rounded-full border border-indigo-400/40 bg-indigo-500/10 px-4 py-2 text-sm font-medium text-indigo-200 transition hover:bg-indigo-500/20"
          >
            查看完整可信度审计 →
          </button>
          <div class="flex flex-wrap gap-3 text-sm text-indigo-300">
            <button @click="openResearch('research', { baseline: `run-${selectedId}` })">参数验证 →</button>
            <button @click="openResearch('market-chart', { run: selectedId })">在K线上查看成交 →</button>
          </div>
          <BacktestAiReview :backtest-id="selectedId" :notify="notify" />
          <!-- 和基准比较：有完整的基准行情时显示两条累计收益曲线，否则只显示资金曲线。 -->
          <h3 v-if="benchmark" class="flex flex-wrap items-center gap-2 text-sm font-semibold text-white">
            <span>和</span>
            <select v-if="benchmarkOptions.length > 1" :value="benchmark.symbol" :disabled="benchmarkLoading" aria-label="基准指数"
              class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-sm font-semibold text-white outline-none focus:border-indigo-400/40 disabled:opacity-60"
              @change="chooseBenchmark($event.target.value, true, $event.target)">
              <option v-for="item in benchmarkOptions" :key="item.value" :value="item.value" class="bg-ink">{{ item.label }}</option>
            </select>
            <span v-else>{{ benchmark.name }}</span>
            <span>比较</span>
          </h3>
          <section v-if="comparisonSeries.length" class="space-y-4" aria-label="和基准比较">
            <div class="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard v-for="card in comparisonCards" :key="card.label" :label="card.label" :value="card.value" :sub="card.sub" :tone="card.tone" />
            </div>
            <div class="rounded-xl border border-white/10 bg-white/5 p-4">
              <div class="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-slate-400">
                <span>累计收益</span>
                <span v-for="line in comparisonSeries" :key="line.label" class="inline-flex items-center gap-1.5">
                  <span class="inline-block h-0.5 w-4" :style="{ backgroundColor: line.color }" />{{ line.label }} {{ line.end }}
                </span>
              </div>
              <LineChart class="mt-2" :series="comparisonSeries" :height="220" :fill="false" />
            </div>
            <p class="text-xs text-slate-400">{{ comparisonNote }}</p>
          </section>
          <template v-else>
            <div class="rounded-xl border border-white/10 bg-white/5 p-4">
              <p class="text-xs text-slate-400">资金曲线</p>
              <LineChart :series="equitySeries" :height="220" />
            </div>
            <p v-if="comparisonNote" class="text-xs text-slate-400">{{ comparisonNote }}</p>
          </template>
        </div>

        <!-- 交易与成本 -->
        <div v-else-if="activeTab === '交易与成本'" class="space-y-5">
          <section class="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="订单数" :value="fmtNum(result.orders)" />
            <MetricCard label="成交笔数" :value="fmtNum(result.fills)" />
            <MetricCard label="胜率" :value="fmtPct(result.win_rate)" :tone="num(result.win_rate) === null ? '' : num(result.win_rate) >= 50 ? 'text-emerald-300' : 'text-rose-300'" />
            <MetricCard label="总交易成本" :value="fmtMoney(totalCost)" />
          </section>
          <div>
            <p class="mb-3 text-xs text-slate-400">交易明细</p>
            <DataTable :columns="tradeCols" :rows="current.trades || []" empty="暂无交易记录" />
          </div>
        </div>

        <!-- 持仓分析 -->
        <div v-else-if="activeTab === '持仓分析'">
          <p class="mb-3 text-xs text-slate-400">当前持仓</p>
          <EmptyState v-if="!(current.positions || []).length" text="暂无持仓" />
          <DataTable v-else :columns="positionCols" :rows="current.positions" empty="暂无持仓" />
        </div>
      </div>
    </SectionCard>
    <details class="glass rounded-2xl p-5">
      <summary class="cursor-pointer text-sm font-semibold text-slate-300">高级工具</summary>
      <div class="mt-4 flex flex-wrap gap-3">
        <button class="rounded-full border border-white/10 px-4 py-2 text-sm text-slate-300 hover:bg-white/5" @click="openResearch('strategy-forensics', { run: selectedId || '' })">成交核查</button>
      </div>
    </details>
  </div>
</template>
