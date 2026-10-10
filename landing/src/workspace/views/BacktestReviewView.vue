<script setup>
import { computed, onActivated, reactive, ref, watch } from 'vue'
import { getBacktestCatalog, getBacktest, getRunAudit, listBacktests, listPackages, submitBacktest } from '../../api.js'
import { openResearch } from '../researchNavigation.js'
import RiskManagementView from './RiskManagementView.vue'
import MetricCard from '../ui/MetricCard.vue'
import SectionCard from '../ui/SectionCard.vue'
import LineChart from '../ui/LineChart.vue'
import EmptyState from '../ui/EmptyState.vue'
import FormField from '../ui/FormField.vue'
import DataTable from '../ui/DataTable.vue'
import StatusPill from '../ui/StatusPill.vue'
import { pendingAuditRun } from '../auditLink.js'

const props = defineProps({
  routeContext: { type: Object, default: () => ({}) },
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

// ---------- 新建回测表单 ----------
const markets = [{ value: '当前股票池', label: '当前 A 股股票池' }]
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
  market: '当前股票池',
  from_date: '2025-01-01',
  to_date: '2025-12-31',
  initial_capital: 1000000,
  max_positions: 10,
  rebalance: 'weekly',
})

const running = ref(false)
const runError = ref('')

// ---------- 历史回测 ----------
const backtests = ref([])
const listLoading = ref(false)
const selectedId = ref(null)
const current = ref(null)
const detailLoading = ref(false)

const result = computed(() => current.value?.result || {})

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

const tabs = ['概览', '收益与风险', '交易与成本', '持仓分析']
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

const metrics = computed(() => {
  const ret = num(result.value.total_return)
  const annual = num(result.value.annual_return)
  const dd = num(result.value.max_drawdown)
  return [
    { label: '最终权益', value: fmtMoney(finalEquity.value), tone: '' },
    { label: '累计收益', value: fmtPct(ret), tone: ret === null ? '' : ret >= 0 ? 'text-emerald-300' : 'text-rose-300' },
    { label: '年化收益', value: fmtPct(annual), tone: annual === null ? '' : annual >= 0 ? 'text-emerald-300' : 'text-rose-300' },
    { label: '最大回撤', value: fmtPct(dd), tone: 'text-rose-300' },
    { label: '夏普比率', value: fmtNum(result.value.sharpe), tone: '' },
    { label: '索提诺比率', value: fmtNum(result.value.sortino), tone: '' },
    { label: '卡玛比率', value: fmtNum(result.value.calmar), tone: '' },
    { label: '总交易成本', value: fmtMoney(totalCost.value), tone: '' },
  ]
})

const equitySeries = computed(() => [
  { label: '资金曲线', color: '#818cf8', points: Array.isArray(result.value.equity) ? result.value.equity : [] },
])

const drawdownNote = computed(() => {
  const r = result.value
  return `本区间策略累计收益 ${fmtPct(r.total_return)}，最大回撤 ${fmtPct(r.max_drawdown)}。最大回撤指资金曲线从峰值到谷底的最大跌幅，是衡量策略下行风险的核心指标：回撤越小，资金曲线越稳健，持有体验越好。`
})

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
async function loadBacktests() {
  listLoading.value = true
  try {
    backtests.value = await listBacktests()
  } catch (e) {
    props.notify(e.message || '加载回测记录失败')
  } finally {
    listLoading.value = false
  }
}

async function loadDetail() {
  if (selectedId.value === null || selectedId.value === '') return
  detailLoading.value = true
  current.value = null
  audit.value = null
  try {
    current.value = await getBacktest(selectedId.value)
    if (props.routeContext.mode === 'reuse') {
      const config = current.value.result?.effective_config
      const reference = config?.strategy_reference || config?.strategy_plugin
      if (reference && strategyOptions.value.some((s) => s.value === reference)) {
        form.strategy = reference
        chooseStrategy()
        for (const key of ['from_date', 'to_date', 'initial_capital', 'max_positions', 'rebalance']) {
          if (config[key] != null) form[key] = config[key]
        }
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
    await loadBacktests()
    selectedId.value = data.id
    await loadDetail()
    activeTab.value = '概览'
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
    catalogErrors.value = catalog.errors || []
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
  if (!props.routeContext.run) return
  const id = Number(String(props.routeContext.run).replace(/^run-/, ''))
  if (!Number.isInteger(id) || id < 1) return
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
  await loadBacktests()
  if (props.routeContext.run) await loadRouteRun()
  else if (backtests.value.length && !selectedId.value) {
    selectedId.value = backtests.value[0].id
    await loadDetail()
  }
})
</script>

<template>
  <div class="space-y-6">
    <!-- 标题 -->
    <div class="glass glass-sheen rounded-2xl p-6">
      <h1 class="text-xl font-bold text-white">策略回测</h1>
      <p class="mt-2 text-sm text-slate-400">统一配置规则策略与 Python 策略，确认后再运行。</p>
      <button class="mt-3 text-sm text-indigo-300" @click="openResearch('strategy-hub')">← 返回我的策略</button>
    </div>

    <!-- 新建回测 -->
    <SectionCard title="新建回测" hint="配置策略与市场区间，运行一次确定性回测">
      <p v-if="routeContext.mode === 'reuse'" class="mb-4 text-sm text-slate-400">已带入历史区间、资金与策略参数；股票池与风控使用当前设置。</p>
      <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <FormField label="策略" type="select" v-model="form.strategy" :options="[{ value: '', label: catalogLoading ? '加载中…' : '请选择策略' }, ...strategyOptions]" :disabled="catalogLoading" @update:model-value="chooseStrategy" />
        <FormField label="市场" type="select" v-model="form.market" :options="markets" />
        <FormField label="开始日期" type="date" v-model="form.from_date" />
        <FormField label="结束日期" type="date" v-model="form.to_date" />
        <FormField label="初始资金" type="number" v-model="form.initial_capital" :min="0" :step="10000" />
        <FormField label="最大持仓" type="number" v-model="form.max_positions" :min="1" :max="form.strategy.startsWith('package:') ? 50 : 500" :step="1" />
        <FormField label="调仓频率" type="select" v-model="form.rebalance" :options="rebalances" />
      </div>
      <p v-for="(error, i) in catalogErrors" :key="i" role="alert" class="mt-3 text-sm text-amber-300">{{ error }}</p>
      <div v-if="selectedStrategy?.parameters?.length" class="mt-5 grid gap-4 border-t border-white/10 pt-5 md:grid-cols-2 xl:grid-cols-4">
        <FormField v-for="p in selectedStrategy.parameters" :key="p.name" v-model="strategyParameters[p.name]" :label="p.label" :type="p.choices?.length ? 'select' : p.kind === 'boolean' ? 'checkbox' : ['integer', 'number'].includes(p.kind) ? 'number' : 'text'" :options="(p.choices || []).map((v) => ({ value: v, label: v }))" :min="p.minimum" :max="p.maximum" :step="p.kind === 'integer' ? 1 : 'any'" :hint="p.description" />
      </div>
      <details :open="riskOpen" class="mt-5 rounded-xl border border-white/10 bg-white/5" @toggle="riskOpen = $event.target.open">
        <summary class="cursor-pointer px-4 py-3 text-sm text-slate-300">风险设置 <span v-if="riskEditor?.dirty" class="text-amber-300">· 有未保存修改</span></summary>
        <div class="p-3 pt-0"><RiskManagementView ref="riskEditor" embedded :user="user" :notify="notify" /></div>
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
    <SectionCard title="回测结果" hint="选择一次历史回测，深入检查收益、风险、交易成本与持仓">
      <template #actions>
        <select
          v-if="backtests.length"
          v-model="selectedId"
          @change="loadDetail"
          class="w-full min-w-[220px] rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-indigo-400/40"
        >
          <option v-for="b in backtests" :key="b.id" :value="b.id" class="bg-ink">
            {{ b.strategy }}｜{{ b.from_date }} ~ {{ b.to_date }}
          </option>
        </select>
      </template>

      <EmptyState v-if="!listLoading && !backtests.length" text="暂无回测记录" />

      <div v-else-if="listLoading" class="text-sm text-slate-400">加载中…</div>

      <div v-else-if="!current" class="text-sm text-slate-500">请在上方选择一次回测查看详情。</div>

      <div v-else class="space-y-4">
        <!-- 元信息 -->
        <div class="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm">
          <span class="text-slate-400">策略</span>
          <span class="font-medium text-white">{{ current.strategy }}</span>
          <span class="text-slate-400">市场</span>
          <span class="text-white">{{ current.market }}</span>
          <span class="text-slate-400">区间</span>
          <span class="text-white">{{ current.from_date }} ~ {{ current.to_date }}</span>
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
          <p>数据状态：{{ result.legacy_unverified ? '旧版未验证' : result.validity_status }}；{{ result.metrics_reliable ? '指标可计算，请结合警告审阅' : '指标不可作为可信结论' }}</p>
          <p v-if="result.effective_config" class="mt-2">实际配置：{{ result.effective_config.strategy_plugin }} · ¥{{ Number(result.effective_config.initial_capital).toLocaleString() }} · 最多 {{ result.effective_config.max_positions }} 只 · {{ rebalances.find(r => r.value === result.effective_config.rebalance)?.label }}调仓 · {{ result.effective_config.from_date }} 至 {{ result.effective_config.to_date }}</p>
          <p v-for="(issue, index) in result.validity_issues || []" :key="index" class="mt-1 text-amber-300">{{ issue.code }}：{{ issue.message }}</p>
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
            <MetricCard label="最大回撤" :value="fmtPct(result.max_drawdown)" tone="text-rose-300" />
            <MetricCard label="可信度评级" :value="gradeValue" :sub="gradeSub" :tone="gradeTone" />
          </section>
          <button
            @click="openAudit"
            class="rounded-full border border-indigo-400/40 bg-indigo-500/10 px-4 py-2 text-sm font-medium text-indigo-200 transition hover:bg-indigo-500/20"
          >
            查看完整可信度审计 →
          </button>
          <div class="flex flex-wrap gap-3 text-sm text-indigo-300">
            <button @click="openResearch('research', { baseline: `run-${selectedId}` })">参数优化 →</button>
            <button @click="openResearch('walk-forward', { baseline: `run-${selectedId}` })">样本外验证 →</button>
            <button @click="openResearch('run-library')">查看研究记录 →</button>
          </div>
          <div class="rounded-xl border border-white/10 bg-white/5 p-4">
            <div class="flex items-center justify-between text-xs text-slate-400">
              <span>资金曲线</span>
              <span class="text-emerald-300">累计收益 {{ fmtPct(result.total_return) }}</span>
            </div>
            <LineChart :series="equitySeries" :height="220" />
          </div>
          <div class="rounded-xl border border-white/10 bg-white/5 p-4">
            <p class="text-xs text-slate-400">回撤说明</p>
            <p class="mt-2 text-sm leading-relaxed text-slate-300">{{ drawdownNote }}</p>
          </div>
        </div>

        <!-- 收益与风险 -->
        <section v-else-if="activeTab === '收益与风险'" class="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard v-for="m in metrics" :key="m.label" :label="m.label" :value="m.value" :tone="m.tone" />
        </section>

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
        <button class="rounded-full border border-white/10 px-4 py-2 text-sm text-slate-300 hover:bg-white/5" @click="openResearch('risk-management')">风控记录与默认配置</button>
      </div>
    </details>
  </div>
</template>
