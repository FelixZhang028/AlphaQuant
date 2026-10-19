<script setup>
import { computed, onActivated, ref, watch } from 'vue'
import { listAuditRuns, localMarketList, runSymbolTrades, runTradedSymbols } from '../../api.js'
import { TRADE_COLORS } from '../klineOverlays.js'
import { formatVolume, quoteSummary } from '../klinePresentation.js'
import { openResearch } from '../researchNavigation.js'
import DataTable from '../ui/DataTable.vue'
import EmptyState from '../ui/EmptyState.vue'
import FormField from '../ui/FormField.vue'
import KlineChart from '../ui/KlineChart.vue'
import SectionCard from '../ui/SectionCard.vue'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
  routeContext: { type: Object, default: () => ({}) },
})

// 链接里的回测编号可能是 12 或 run-12，统一成接口使用的 run-12。
const runReference = (value) => (value ? `run-${String(value).replace(/^run-/, '')}` : '')

// ---------- 股票列表 ----------
const SCOPES = [{ key: 'all', label: '全部股票' }, { key: 'universe', label: '股票池' }]
const searchText = ref('')
const query = ref('')
const scope = ref('all')
const listLoading = ref(true)
const listError = ref('')
const catalog = ref({ items: [], total: 0, page: 1, pages: 1 })
let listRequest = 0

// 当前股票以链接中的代码为准；链接里没有时，取列表中第一只有行情的股票。
const symbol = ref(props.routeContext.symbol || '')
const data = ref(null)

async function load(page = catalog.value.page) {
  const request = ++listRequest
  listLoading.value = true
  listError.value = ''
  try {
    const response = await localMarketList({ q: query.value, scope: scope.value, page, page_size: 30 })
    if (request !== listRequest) return
    catalog.value = response
    if (!symbol.value && !run.value) symbol.value = (response.items.find((row) => row.rows) || {}).symbol || ''
  } catch (e) {
    if (request === listRequest) listError.value = e.message || '读取股票列表失败'
  } finally {
    if (request === listRequest) listLoading.value = false
  }
}
function search() {
  query.value = searchText.value.trim()
  if (!run.value) load(1)
}
function changeScope(key) {
  scope.value = key
  load(1)
}
function syncUrl() {
  openResearch('market-chart', { symbol: symbol.value, run: run.value })
}
function choose(row) {
  if (row.symbol === symbol.value) return
  symbol.value = row.symbol
  syncUrl()
}
function navigate(key) {
  window.dispatchEvent(new CustomEvent('fq-navigate', { detail: key }))
}

// ---------- 叠加一次回测 ----------
// 旧版后端没有这些接口时返回的是通用的 404，直接显示会让人看不懂。
const failure = (e, fallback) => (e.status === 404 && e.data?.detail === 'Not Found'
  ? '后端服务还没有回测成交接口，请重启后端后重试。' : e.message || fallback)
const runs = ref([])
const run = ref(runReference(props.routeContext.run))
const traded = ref(null)
const tradedError = ref('')
const trades = ref(null)
const tradesError = ref('')
const chart = ref(null)
let tradedRequest = 0
let tradesRequest = 0

const runOptions = computed(() => {
  const options = runs.value.map((item) => ({ value: item.run_id, label: item.run_label }))
  // 链接指向的回测不在列表里时仍然显示出来，避免下拉框显示成“不叠加”。
  if (run.value && !options.some((item) => item.value === run.value)) options.unshift({ value: run.value, label: traded.value?.run_label || run.value })
  return [{ value: '', label: '不叠加回测' }, ...options]
})
async function loadRuns() {
  try {
    runs.value = (await listAuditRuns()).items
  } catch {
    // 回测列表读不到时，行情图表本身仍然可用。
    runs.value = []
  }
}
async function loadTraded() {
  const request = ++tradedRequest
  traded.value = null
  tradedError.value = ''
  if (!run.value) return
  try {
    const response = await runTradedSymbols(run.value)
    if (request !== tradedRequest) return
    traded.value = response
    // 当前股票不在这次回测里时，换到成交最多的一只。
    if (response.symbols.length && !response.symbols.some((row) => row.symbol === symbol.value)) {
      symbol.value = response.symbols[0].symbol
      syncUrl()
    }
  } catch (e) {
    if (request === tradedRequest) tradedError.value = failure(e, '读取回测成交失败')
  }
}
async function loadTrades() {
  const request = ++tradesRequest
  trades.value = null
  tradesError.value = ''
  if (!run.value || !symbol.value) return
  try {
    const response = await runSymbolTrades(run.value, symbol.value)
    if (request === tradesRequest) trades.value = response
  } catch (e) {
    if (request === tradesRequest) tradesError.value = failure(e, '读取这只股票的成交失败')
  }
}
function changeRun(value) {
  run.value = value
  syncUrl()
}

// 列表：叠加回测时只列出这次回测交易过的股票，搜索在本地过滤。
const rows = computed(() => {
  if (!run.value) return catalog.value.items.map((row) => ({ ...row, note: row.rows ? row.symbol : '未下载' }))
  const keyword = query.value.toLowerCase()
  return (traded.value?.symbols || [])
    .filter((row) => !keyword || row.symbol.includes(keyword) || row.name.toLowerCase().includes(keyword))
    .map((row) => ({ ...row, note: `买${row.buys} 卖${row.sells}${row.rejected ? ` 拒${row.rejected}` : ''}` }))
})
const listMessage = computed(() => {
  if (run.value) {
    if (tradedError.value) return ''
    if (!traded.value) return '正在读取这次回测交易过的股票…'
    if (!traded.value.symbols.length) return '这次回测没有任何成交或未成交订单。'
    return rows.value.length ? '' : '没有找到匹配的股票。'
  }
  if (listLoading.value && !catalog.value.items.length) return '正在读取股票列表…'
  if (listError.value) return ''
  if (!catalog.value.items.length) return query.value ? '没有找到匹配的股票。' : scope.value === 'all' ? '本地暂无已下载行情。' : '股票池为空。'
  return ''
})

// ---------- 当前股票 ----------
const name = computed(() => data.value?.name
  || rows.value.find((row) => row.symbol === symbol.value)?.name || '')
const quote = computed(() => (data.value ? quoteSummary(data.value.bars) : null))
const price = (value) => (value == null ? '—' : value.toFixed(2))
const percent = (value) => (value == null ? '—' : `${value > 0 ? '+' : ''}${(value * 100).toFixed(2)}%`)
// A 股习惯：红涨绿跌。
const tone = (value) => (value > 0 ? 'text-rose-300' : value < 0 ? 'text-emerald-300' : 'text-slate-300')
const facts = computed(() => {
  const q = quote.value
  if (!q) return []
  return [
    { label: '开盘', value: price(q.open) }, { label: '最高', value: price(q.high) },
    { label: '最低', value: price(q.low) }, { label: '成交量', value: `${formatVolume(q.volume)}股` },
  ]
})
const periods = computed(() => {
  const q = quote.value
  if (!q) return []
  return [{ label: '近20个交易日', value: q.pct20 }, { label: '近60个交易日', value: q.pct60 }, { label: '近250个交易日', value: q.pct250 }]
})

// ---------- 这只股票在回测中的记录 ----------
const tradeColumns = [
  { key: 'date', label: '日期' }, { key: 'action', label: '方向' }, { key: 'price', label: '成交价（不复权）', align: 'right' },
  { key: 'quantity', label: '数量（股）', align: 'right' }, { key: 'fees', label: '税费（元）', align: 'right' },
  { key: 'slippage', label: '滑点与冲击（元）', align: 'right' }, { key: 'note', label: '说明' },
]
const money = (value) => (value == null ? '—' : value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
const tradeRows = computed(() => {
  if (!trades.value) return []
  const side = (value) => (value === 'BUY' ? '买入' : '卖出')
  return [
    ...trades.value.fills.map((fill) => ({
      date: fill.date, action: side(fill.side), buy: fill.side === 'BUY', price: fill.price.toFixed(2),
      quantity: fill.quantity.toLocaleString('zh-CN'), fees: money(fill.fees), slippage: money(fill.slippage_cost), note: '',
    })),
    ...trades.value.rejected.map((order) => ({
      date: order.date, action: `${side(order.side)}未成交`, rejected: true, price: '—',
      quantity: order.quantity.toLocaleString('zh-CN'), fees: '—', slippage: '—', note: order.reason_label,
    })),
  ].sort((a, b) => a.date.localeCompare(b.date))
})
const tradeSummary = computed(() => {
  if (!trades.value) return ''
  const { fills, rejected } = trades.value
  const buys = fills.filter((fill) => fill.side === 'BUY').length
  const total = (key) => money(fills.reduce((sum, fill) => sum + (fill[key] || 0), 0))
  return `买入 ${buys} 次 · 卖出 ${fills.length - buys} 次 · 未成交 ${rejected.length} 次 · 税费合计 ${total('fees')} 元 · 滑点与冲击合计 ${total('slippage_cost')} 元`
})

// 只接受链接里非空的值：从侧栏回到本页时，保留上次看的股票和回测。
watch(() => [props.routeContext.symbol, props.routeContext.run], ([nextSymbol, nextRun]) => {
  if (nextSymbol && nextSymbol !== symbol.value) symbol.value = nextSymbol
  if (nextRun && runReference(nextRun) !== run.value) run.value = runReference(nextRun)
})
watch(symbol, () => { data.value = null })
watch(run, loadTraded, { immediate: true })
watch([run, symbol], loadTrades, { immediate: true })
onActivated(() => {
  load()
  loadRuns()
})
</script>

<template>
  <div class="grid gap-5 lg:grid-cols-[15rem_minmax(0,1fr)] xl:grid-cols-[15rem_minmax(0,1fr)_15rem]">
    <SectionCard title="选择股票" :hint="run ? '只列出这次回测交易过的股票' : '只显示本地已有的行情'">
      <FormField label="叠加回测成交" type="select" :model-value="run" :options="runOptions" @update:model-value="changeRun" />
      <p v-if="tradedError" class="mt-2 text-sm text-rose-300" role="alert">{{ tradedError }} <button type="button" class="underline" @click="loadTraded">重试</button></p>
      <div v-if="!run" class="mt-3 flex flex-wrap gap-2" role="group" aria-label="股票范围">
        <button v-for="item in SCOPES" :key="item.key" type="button" :aria-pressed="scope === item.key"
          class="rounded-full border px-3 py-1 text-xs transition"
          :class="scope === item.key ? 'border-indigo-400/40 bg-indigo-500/20 text-indigo-200' : 'border-white/10 bg-white/5 text-slate-300 hover:bg-white/10'"
          @click="changeScope(item.key)">{{ item.label }}</button>
      </div>
      <form class="mt-3" @submit.prevent="search">
        <input v-model="searchText" aria-label="搜索股票" placeholder="名称或代码，回车搜索" maxlength="80"
          class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-indigo-400/40" />
      </form>
      <p v-if="!run && listError" class="mt-4 text-sm text-rose-300" role="alert">{{ listError }} <button type="button" class="underline" @click="load()">重试</button></p>
      <p v-if="listMessage" class="mt-4 text-sm text-slate-400" role="status">{{ listMessage }}</p>
      <ul v-if="rows.length" class="mt-3 max-h-56 space-y-0.5 overflow-y-auto pr-1 lg:max-h-[34rem]" aria-label="股票列表">
        <li v-for="row in rows" :key="row.symbol">
          <button type="button" :aria-current="row.symbol === symbol ? 'true' : undefined"
            class="flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm transition"
            :class="row.symbol === symbol ? 'bg-indigo-500/20 text-indigo-200' : 'text-slate-300 hover:bg-white/5'"
            @click="choose(row)">
            <span class="truncate">{{ row.name }}</span>
            <span class="shrink-0 text-xs text-slate-500">{{ row.note }}</span>
          </button>
        </li>
      </ul>
      <template v-if="!run && catalog.items.length">
        <p class="mt-3 text-xs text-slate-400">共 {{ catalog.total }} 只 · 第 {{ catalog.page }} / {{ catalog.pages }} 页</p>
        <div class="mt-2 flex gap-2 text-xs text-slate-400">
          <button type="button" class="flex-1 whitespace-nowrap rounded-lg border border-white/10 px-2 py-1.5 transition hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40" :disabled="listLoading || catalog.page <= 1" @click="load(catalog.page - 1)">上一页</button>
          <button type="button" class="flex-1 whitespace-nowrap rounded-lg border border-white/10 px-2 py-1.5 transition hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40" :disabled="listLoading || catalog.page >= catalog.pages" @click="load(catalog.page + 1)">下一页</button>
        </div>
      </template>
      <p v-else-if="run && traded" class="mt-3 text-xs text-slate-400">共 {{ traded.symbols.length }} 只 · {{ traded.run_label }}</p>
    </SectionCard>

    <section class="glass min-w-0 rounded-2xl p-5" aria-label="K线图">
      <template v-if="symbol">
        <h2 class="text-lg font-semibold text-white">{{ name || '…' }} · {{ symbol }}</h2>
        <KlineChart ref="chart" class="mt-4" :symbol="symbol" :trades="trades" @loaded="data = $event" />
        <div v-if="run" class="mt-5 border-t border-white/10 pt-4" aria-label="回测记录">
          <h3 class="text-sm font-semibold text-white">这只股票在本次回测中的记录</h3>
          <p v-if="tradesError" class="mt-2 text-sm text-rose-300" role="alert">{{ tradesError }} <button type="button" class="underline" @click="loadTrades">重试</button></p>
          <p v-else-if="!trades" class="mt-2 text-sm text-slate-400" role="status">正在读取…</p>
          <template v-else>
            <p class="mt-1 text-xs text-slate-400">{{ tradeSummary }}。点击日期可在图上定位。</p>
            <div class="mt-3 max-h-72 overflow-y-auto">
              <DataTable :columns="tradeColumns" :rows="tradeRows" empty="这只股票在本次回测中没有交易记录。">
                <template #cell-date="{ row }"><button type="button" class="whitespace-nowrap text-indigo-300 hover:underline" @click="chart?.focus(row.date)">{{ row.date }}</button></template>
                <template #cell-action="{ row }"><span class="whitespace-nowrap" :class="{ 'text-slate-400': row.rejected }" :style="row.rejected ? undefined : { color: row.buy ? TRADE_COLORS.buy : TRADE_COLORS.sell }">{{ row.action }}</span></template>
              </DataTable>
            </div>
          </template>
        </div>
      </template>
      <template v-else-if="run ? traded || tradedError : !listLoading && !listError">
        <EmptyState :text="run ? '这次回测没有可以显示的股票。' : '平台还没有可以查看的行情，管理员更新后就能看。'" />
        <button v-if="!run" type="button" class="mt-4 text-sm text-indigo-300 hover:underline" @click="navigate('data-guide')">看数据说明</button>
      </template>
    </section>

    <SectionCard title="行情摘要" :hint="quote ? `截至 ${quote.date}` : ''" class="lg:col-span-2 xl:col-span-1">
      <p v-if="!quote" class="text-sm text-slate-400">{{ symbol ? '读取行情后显示。' : '暂无数据。' }}</p>
      <template v-else>
        <p class="text-3xl font-semibold" :class="tone(quote.changePct)">{{ price(quote.close) }}</p>
        <p class="mt-1 text-sm" :class="tone(quote.changePct)">
          {{ quote.change == null ? '—' : `${quote.change > 0 ? '+' : ''}${quote.change.toFixed(2)}` }} · {{ percent(quote.changePct) }}
        </p>
        <dl class="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-sm sm:grid-cols-4 xl:grid-cols-2">
          <div v-for="item in facts" :key="item.label">
            <dt class="text-xs text-slate-500">{{ item.label }}</dt>
            <dd class="mt-0.5 text-slate-200">{{ item.value }}</dd>
          </div>
        </dl>
        <h3 class="mt-5 border-t border-white/10 pt-4 text-xs font-medium text-slate-500">区间涨跌</h3>
        <dl class="mt-2 space-y-2 text-sm">
          <div v-for="item in periods" :key="item.label" class="flex items-center justify-between gap-2">
            <dt class="text-slate-400">{{ item.label }}</dt>
            <dd :class="tone(item.value)">{{ percent(item.value) }}</dd>
          </div>
        </dl>
        <p class="mt-4 text-xs leading-5 text-slate-500">
          {{ data.adjust === 'forward' ? '按前复权价格计算，区间涨跌已包含分红送转。' : '按不复权价格计算，除权除息日会出现价格缺口。' }}本地日线不是实时行情。
        </p>
      </template>
    </SectionCard>
  </div>
</template>
