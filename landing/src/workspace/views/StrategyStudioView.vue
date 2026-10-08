<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  backtestPackage,
  copyPackage,
  createPackage,
  listPackages,
  preflightPackage,
  studioOptions,
} from '../../api.js'
import MetricCard from '../ui/MetricCard.vue'
import SectionCard from '../ui/SectionCard.vue'
import DataTable from '../ui/DataTable.vue'
import LineChart from '../ui/LineChart.vue'
import FormField from '../ui/FormField.vue'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

const options = ref(null)
const activeTab = ref('template')
const tabs = [
  { key: 'template', label: '模板快速回测' },
  { key: 'builder', label: '积木创建' },
  { key: 'saved', label: '已保存策略' },
]

// ---------- 选项映射 ----------
const freqOptions = [
  { value: 'daily', label: '每日' },
  { value: 'weekly', label: '每周' },
  { value: 'monthly', label: '每月' },
]
const dirOptions = [
  { value: 'descending', label: '降序' },
  { value: 'ascending', label: '升序' },
]
const styleOptions = [
  { value: 'conservative', label: '保守' },
  { value: 'balanced', label: '均衡' },
  { value: 'aggressive', label: '激进' },
]
const logicOptions = [
  { value: 'all', label: '全部满足' },
  { value: 'any', label: '任意满足' },
]

const templateOptions = computed(() =>
  (options.value?.templates || []).map((t) => ({ value: t.template_id, label: t.name }))
)
const indicatorOptions = computed(() => {
  const ind = options.value?.indicators || {}
  return Object.keys(ind).map((k) => ({ value: k, label: ind[k] }))
})
const operatorOptions = computed(() => {
  const op = options.value?.operators || {}
  return Object.keys(op).map((k) => ({ value: k, label: op[k] }))
})

// ---------- Tab 1：模板快速回测 ----------
const tpl = reactive({
  template_id: '',
  style: 'balanced',
  start_date: '2025-01-01',
  end_date: '2026-01-01',
  initial_cash: 1000000,
  top_n: 10,
  rebalance: 'weekly',
  running: false,
})
const tplResult = ref(null)

const currentTemplate = computed(() =>
  (options.value?.templates || []).find((t) => t.template_id === tpl.template_id)
)

watch(
  () => tpl.template_id,
  (id) => {
    const t = (options.value?.templates || []).find((x) => x.template_id === id)
    if (t) {
      if (t.top_n != null) tpl.top_n = t.top_n
      if (t.rebalance) tpl.rebalance = t.rebalance
    }
  }
)

async function runTemplate() {
  if (!tpl.template_id) return props.notify('请选择模板')
  tpl.running = true
  tplResult.value = null
  try {
    const t = currentTemplate.value
    const pkg = await createPackage({
      definition: {
        name: t.name,
        entry_logic: 'all',
        entry_rules: [],
        ranking: { indicator: { name: 'return_1d', window: 20 }, direction: 'descending' },
      },
      top_n: Number(tpl.top_n),
      rebalance: tpl.rebalance,
      source: `template:${tpl.template_id}`,
    })
    const run = await backtestPackage(pkg.package_id, {
      start_date: tpl.start_date,
      end_date: tpl.end_date,
      initial_cash: Number(tpl.initial_cash),
      style: tpl.style,
    })
    tplResult.value = run.summary
    props.notify('模板回测完成')
    loadSaved()
  } catch (e) {
    props.notify(e.message || '回测失败')
  } finally {
    tpl.running = false
  }
}

// ---------- Tab 2：积木创建 ----------
const bd = reactive({
  name: '',
  entry_logic: 'all',
  condition_count: 2,
  rules: Array.from({ length: 6 }, () => ({ indicator: '', operator: '', value: 0 })),
  ranking_indicator: '',
  ranking_direction: 'descending',
  top_n: 10,
  rebalance: 'weekly',
})
const bdWarnings = ref(null)
const bdChecking = ref(false)
const bdSaving = ref(false)

const conditionCount = computed(() => {
  const n = parseInt(bd.condition_count, 10)
  return Math.min(6, Math.max(1, Number.isNaN(n) ? 1 : n))
})

function buildBuilderPayload() {
  const entry_rules = bd.rules.slice(0, conditionCount.value).map((r) => ({
    left: { name: r.indicator },
    operator: r.operator,
    value: Number(r.value),
  }))
  return {
    definition: {
      name: bd.name,
      entry_logic: bd.entry_logic,
      entry_rules,
      ranking: { indicator: { name: bd.ranking_indicator }, direction: bd.ranking_direction },
    },
    top_n: Number(bd.top_n),
    rebalance: bd.rebalance,
    source: 'visual_builder',
  }
}

async function runPreflight() {
  if (!bd.name.trim()) return props.notify('请输入策略名称')
  bdChecking.value = true
  bdWarnings.value = null
  try {
    const res = await preflightPackage(buildBuilderPayload())
    bdWarnings.value = res
  } catch (e) {
    props.notify(e.message || '检查失败')
  } finally {
    bdChecking.value = false
  }
}

async function saveBuilder() {
  if (!bd.name.trim()) return props.notify('请输入策略名称')
  bdSaving.value = true
  try {
    await createPackage(buildBuilderPayload())
    props.notify('策略已保存')
    bd.name = ''
    bdWarnings.value = null
    activeTab.value = 'saved'
    loadSaved()
  } catch (e) {
    props.notify(e.message || '保存失败')
  } finally {
    bdSaving.value = false
  }
}

// ---------- Tab 3：已保存策略 ----------
const savedItems = ref([])
const savedLoading = ref(false)
const savedCols = [
  { key: 'name', label: '名称' },
  { key: 'package_id', label: 'package_id' },
  { key: 'source', label: '来源' },
  { key: 'rebalance', label: '调仓频率' },
  { key: 'actions', label: '操作', align: 'right' },
]
const savedBacktest = reactive({ id: null, running: false, summary: null })

const freqLabel = (v) => freqOptions.find((o) => o.value === v)?.label || v || '—'

function sourceLabel(src) {
  if (!src) return '—'
  if (src === 'visual_builder') return '积木创建'
  if (String(src).startsWith('template:')) return '模板'
  return src
}

async function loadSaved() {
  savedLoading.value = true
  try {
    const res = await listPackages()
    savedItems.value = res.items || []
  } catch (e) {
    props.notify(e.message || '加载失败')
  } finally {
    savedLoading.value = false
  }
}

async function onCopy(pkg) {
  try {
    const name = prompt('复制为新策略，可输入新名称（留空自动命名）', `${pkg.name}（副本）`)
    await copyPackage(pkg.package_id, name || undefined)
    await loadSaved()
    props.notify('已复制为新策略')
  } catch (e) {
    props.notify(e.message || '复制失败')
  }
}

async function onBacktestSaved(pkg) {
  savedBacktest.id = pkg.package_id
  savedBacktest.running = true
  savedBacktest.summary = null
  try {
    const run = await backtestPackage(pkg.package_id)
    savedBacktest.summary = run.summary
    props.notify('回测完成')
  } catch (e) {
    props.notify(e.message || '回测失败')
  } finally {
    savedBacktest.running = false
  }
}

// ---------- 指标展示 ----------
function fmtPct(v, signed = false) {
  if (v == null || v === '') return '—'
  const n = Number(v)
  if (Number.isNaN(n)) return '—'
  return `${signed && n >= 0 ? '+' : ''}${n.toFixed(2)}%`
}
function fmtNum(v, digits = 2) {
  if (v == null || v === '') return '—'
  const n = Number(v)
  return Number.isNaN(n) ? '—' : n.toFixed(digits)
}
function tradeCount(s) {
  if (s == null) return '—'
  if (s.trade_count != null) return s.trade_count
  if (s.num_trades != null) return s.num_trades
  if (Array.isArray(s.trades)) return s.trades.length
  if (s.trades != null) return s.trades
  return '—'
}
function buildMetrics(s) {
  if (!s) return []
  const tr = Number(s.total_return)
  const up = !Number.isNaN(tr) && tr >= 0
  return [
    { label: '累计收益', value: fmtPct(s.total_return, true), up, tone: up ? 'text-emerald-300' : 'text-rose-300' },
    { label: '最大回撤', value: fmtPct(s.max_drawdown), up: null, tone: 'text-rose-300' },
    { label: '夏普比率', value: fmtNum(s.sharpe), up: null, tone: 'text-white' },
    { label: '成交笔数', value: tradeCount(s), up: null, tone: 'text-white' },
  ]
}
const tplMetrics = computed(() => buildMetrics(tplResult.value))
const savedMetrics = computed(() => buildMetrics(savedBacktest.summary))

onMounted(async () => {
  try {
    options.value = await studioOptions()
    const indKeys = Object.keys(options.value.indicators || {})
    const opKeys = Object.keys(options.value.operators || {})
    bd.ranking_indicator = indKeys[0] || ''
    bd.rules = Array.from({ length: 6 }, () => ({
      indicator: indKeys[0] || '',
      operator: opKeys[0] || '',
      value: 0,
    }))
    if (options.value.templates?.length) tpl.template_id = options.value.templates[0].template_id
  } catch (e) {
    props.notify(e.message || '加载选项失败')
  }
  loadSaved()
})
</script>

<template>
  <div class="space-y-6">
    <!-- 标题 -->
    <div class="glass relative overflow-hidden rounded-2xl p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-indigo-500/20 blur-3xl" />
      <p class="text-sm text-slate-400">策略研究</p>
      <h1 class="mt-1 text-2xl font-bold text-white">模板与积木</h1>
      <p class="mt-2 max-w-2xl text-sm text-slate-400">6 套内置模板一键回测、积木式规则编辑、已保存策略复用</p>
    </div>

    <!-- 分段按钮 Tab -->
    <div class="flex w-fit rounded-full border border-white/10 bg-white/5 p-0.5 text-xs">
      <button
        v-for="t in tabs"
        :key="t.key"
        @click="activeTab = t.key"
        class="rounded-full px-3 py-1 transition"
        :class="activeTab === t.key ? 'bg-gradient-to-r from-indigo-500 to-violet-500 text-white' : 'text-slate-400 hover:text-slate-200'"
      >
        {{ t.label }}
      </button>
    </div>

    <!-- Tab 1：模板快速回测 -->
    <template v-if="activeTab === 'template'">
      <div v-if="!options" class="text-sm text-slate-400">加载中…</div>
      <template v-else>
        <SectionCard title="模板快速回测" hint="选择内置模板与参数，一键生成回测结果">
          <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <FormField label="模板" type="select" v-model="tpl.template_id" :options="templateOptions" />
            <FormField label="风格" type="select" v-model="tpl.style" :options="styleOptions" />
            <FormField label="开始日期" type="date" v-model="tpl.start_date" />
            <FormField label="结束日期" type="date" v-model="tpl.end_date" />
            <FormField label="初始资金" type="number" v-model="tpl.initial_cash" :min="0" :step="10000" />
            <FormField label="持股数量" type="number" v-model="tpl.top_n" :min="1" :max="100" />
            <FormField label="调仓频率" type="select" v-model="tpl.rebalance" :options="freqOptions" />
          </div>

          <div v-if="currentTemplate" class="mt-4 rounded-xl border border-white/10 bg-white/5 p-4">
            <p class="text-sm text-slate-300">{{ currentTemplate.summary }}</p>
            <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
              <span class="text-slate-400">适合市场：{{ currentTemplate.suitable_market || '—' }}</span>
              <span class="text-amber-300">主要风险：{{ currentTemplate.main_risk || '—' }}</span>
              <span class="text-slate-400">风格：{{ styleOptions.find((s) => s.value === tpl.style)?.label || '—' }}</span>
            </div>
          </div>

          <button
            @click="runTemplate"
            :disabled="tpl.running"
            class="mt-5 rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
          >
            {{ tpl.running ? '回测中…' : '开始模板回测' }}
          </button>
        </SectionCard>

        <div v-if="tplResult" class="mt-6 space-y-5">
          <section class="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              v-for="m in tplMetrics"
              :key="m.label"
              :label="m.label"
              :value="m.value"
              :up="m.up"
              :tone="m.tone"
            />
          </section>
          <div class="glass rounded-2xl p-5">
            <h2 class="text-sm font-semibold text-white">资金曲线</h2>
            <div class="mt-4">
              <LineChart :series="[{ label: '资金曲线', color: '#818cf8', points: tplResult.equity || [] }]" :height="180" />
            </div>
          </div>
        </div>
      </template>
    </template>

    <!-- Tab 2：积木创建 -->
    <template v-else-if="activeTab === 'builder'">
      <div v-if="!options" class="text-sm text-slate-400">加载中…</div>
      <template v-else>
        <SectionCard title="积木创建" hint="用条件积木搭建策略规则，生成并检查后保存">
          <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <FormField label="策略名称" v-model="bd.name" placeholder="如 动量 + 均线策略" />
            <FormField label="条件组合" type="select" v-model="bd.entry_logic" :options="logicOptions" />
            <FormField label="条件数量（1-6）" type="number" v-model="bd.condition_count" :min="1" :max="6" />
            <FormField label="持股数量" type="number" v-model="bd.top_n" :min="1" :max="100" />
          </div>

          <div class="mt-4 space-y-3">
            <div
              v-for="i in conditionCount"
              :key="i"
              class="rounded-xl border border-white/10 bg-white/5 p-4"
            >
              <p class="text-xs text-slate-400">条件 {{ i }}</p>
              <div class="mt-3 grid gap-4 md:grid-cols-3">
                <FormField label="指标" type="select" v-model="bd.rules[i - 1].indicator" :options="indicatorOptions" />
                <FormField label="判断" type="select" v-model="bd.rules[i - 1].operator" :options="operatorOptions" />
                <FormField label="比较数值" type="number" v-model="bd.rules[i - 1].value" :step="0.01" />
              </div>
            </div>
          </div>

          <div class="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <FormField label="排序指标" type="select" v-model="bd.ranking_indicator" :options="indicatorOptions" />
            <FormField label="排序方向" type="select" v-model="bd.ranking_direction" :options="dirOptions" />
            <FormField label="调仓频率" type="select" v-model="bd.rebalance" :options="freqOptions" />
          </div>

          <div v-if="bdWarnings" class="mt-4 rounded-xl border border-amber-400/20 bg-amber-400/5 p-4">
            <p class="text-xs text-amber-300">
              检查结果：{{ bdWarnings.warnings?.length ? `${bdWarnings.warnings.length} 条提示` : '未发现明显问题' }}
            </p>
            <ul v-if="bdWarnings.warnings?.length" class="mt-2 space-y-1">
              <li v-for="(w, i) in bdWarnings.warnings" :key="i" class="text-xs text-slate-300">• {{ w }}</li>
            </ul>
            <p v-if="bdWarnings.minimum_history_days" class="mt-2 text-xs text-slate-500">
              建议最低历史数据：{{ bdWarnings.minimum_history_days }} 天
            </p>
          </div>

          <div class="mt-5 flex flex-wrap gap-3">
            <button
              @click="runPreflight"
              :disabled="bdChecking"
              class="rounded-full border border-white/10 px-4 py-2 text-sm text-slate-300 transition hover:bg-white/5 disabled:opacity-70"
            >
              {{ bdChecking ? '检查中…' : '生成并检查策略' }}
            </button>
            <button
              @click="saveBuilder"
              :disabled="bdSaving"
              class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
            >
              {{ bdSaving ? '保存中…' : '保存策略' }}
            </button>
          </div>
        </SectionCard>
      </template>
    </template>

    <!-- Tab 3：已保存策略 -->
    <template v-else>
      <SectionCard title="已保存策略" hint="复用已保存的策略：复制为新策略或直接回测">
        <DataTable :columns="savedCols" :rows="savedItems" empty="暂无已保存策略">
          <template #cell-package_id="{ value }">
            <span class="font-mono text-xs text-indigo-300">{{ value }}</span>
          </template>
          <template #cell-source="{ value }">
            <span class="text-slate-400">{{ sourceLabel(value) }}</span>
          </template>
          <template #cell-rebalance="{ value }">
            <span class="text-slate-400">{{ freqLabel(value) }}</span>
          </template>
          <template #cell-actions="{ row }">
            <div class="flex justify-end gap-2">
              <button
                @click="onCopy(row)"
                class="rounded-lg border border-white/10 px-2.5 py-1 text-xs text-slate-300 transition hover:bg-white/10 hover:text-white"
              >
                复制为新策略
              </button>
              <button
                @click="onBacktestSaved(row)"
                :disabled="savedBacktest.running && savedBacktest.id === row.package_id"
                class="rounded-lg border border-indigo-400/20 px-2.5 py-1 text-xs text-indigo-300 transition hover:bg-indigo-400/10 disabled:opacity-50"
              >
                {{ savedBacktest.running && savedBacktest.id === row.package_id ? '回测中…' : '回测已保存策略' }}
              </button>
            </div>
          </template>
        </DataTable>
      </SectionCard>

      <div v-if="savedBacktest.summary" class="mt-6 space-y-5">
        <section class="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            v-for="m in savedMetrics"
            :key="m.label"
            :label="m.label"
            :value="m.value"
            :up="m.up"
            :tone="m.tone"
          />
        </section>
        <div class="glass rounded-2xl p-5">
          <h2 class="text-sm font-semibold text-white">资金曲线</h2>
          <div class="mt-4">
            <LineChart :series="[{ label: '资金曲线', color: '#818cf8', points: savedBacktest.summary.equity || [] }]" :height="180" />
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
