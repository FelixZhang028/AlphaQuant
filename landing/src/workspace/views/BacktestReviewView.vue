<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { getBacktest, listBacktests, submitBacktest } from '../../api.js'
import MetricCard from '../ui/MetricCard.vue'
import SectionCard from '../ui/SectionCard.vue'
import LineChart from '../ui/LineChart.vue'
import EmptyState from '../ui/EmptyState.vue'
import FormField from '../ui/FormField.vue'
import DataTable from '../ui/DataTable.vue'
import StatusPill from '../ui/StatusPill.vue'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

// ---------- 新建回测表单 ----------
const markets = [
  { value: '沪深300', label: '沪深300' },
  { value: '中证500', label: '中证500' },
  { value: '纳指100', label: '纳指100' },
]
const rebalances = [
  { value: 'daily', label: '每日' },
  { value: 'weekly', label: '每周' },
  { value: 'monthly', label: '每月' },
]

const form = reactive({
  strategy: 'AlphaSeeker',
  market: '沪深300',
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
  try {
    current.value = await getBacktest(selectedId.value)
  } catch (e) {
    props.notify(e.message || '加载回测详情失败')
  } finally {
    detailLoading.value = false
  }
}

async function onSubmit() {
  if (!form.strategy.trim()) return props.notify('请输入策略名称')
  if (form.from_date >= form.to_date) return props.notify('开始日期需早于结束日期')
  running.value = true
  runError.value = ''
  try {
    const data = await submitBacktest({
      strategy: form.strategy.trim(),
      market: form.market,
      from_date: form.from_date,
      to_date: form.to_date,
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

onMounted(async () => {
  await loadBacktests()
  if (backtests.value.length) {
    selectedId.value = backtests.value[0].id
    await loadDetail()
  }
})
</script>

<template>
  <div class="space-y-6">
    <!-- 标题 -->
    <div>
      <h1 class="text-xl font-bold text-white">回测与验证</h1>
      <p class="mt-1 text-sm text-slate-400">运行一组确定参数，深入检查收益、风险、交易成本、持仓与订单</p>
    </div>

    <!-- 新建回测 -->
    <SectionCard title="新建回测" hint="配置策略与市场区间，运行一次确定性回测">
      <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <FormField label="策略" v-model="form.strategy" placeholder="如 AlphaSeeker" />
        <FormField label="市场" type="select" v-model="form.market" :options="markets" />
        <FormField label="开始日期" type="date" v-model="form.from_date" />
        <FormField label="结束日期" type="date" v-model="form.to_date" />
        <FormField label="初始资金" type="number" v-model="form.initial_capital" :min="0" :step="10000" />
        <FormField label="最大持仓" type="number" v-model="form.max_positions" :min="1" :step="1" />
        <FormField label="调仓频率" type="select" v-model="form.rebalance" :options="rebalances" />
      </div>
      <p v-if="runError" class="mt-4 text-sm text-rose-300">{{ runError }}</p>
      <div class="mt-5 flex justify-end">
        <button
          @click="onSubmit"
          :disabled="running"
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

        <!-- 概览 -->
        <div v-else-if="activeTab === '概览'" class="space-y-4">
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
  </div>
</template>
