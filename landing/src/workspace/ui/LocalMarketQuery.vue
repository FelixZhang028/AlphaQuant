<script setup>
import { computed, nextTick, onActivated, ref } from 'vue'
import { localMarketList, localMarketDetail, updateLocalStock, universeAdd } from '../../api.js'
import SectionCard from './SectionCard.vue'
import DataTable from './DataTable.vue'
import FormField from './FormField.vue'

const props = defineProps({ notify: { type: Function, default: () => {} } })
const emit = defineEmits(['changed'])
const searchText = ref('')
const query = ref('')
const scope = ref('all')
const loading = ref(true)
const error = ref('')
const catalog = ref({ items: [], total: 0, page: 1, pages: 1, downloaded_count: 0, universe_count: 0 })
const loaded = ref(false)
const addingSymbol = ref('')
let listRequest = 0
const columns = [
  { key: 'name', label: '股票名称' }, { key: 'symbol', label: '代码' },
  { key: 'start_date', label: '开始日期' }, { key: 'end_date', label: '截至日期' },
  { key: 'status', label: '数据状态' }, { key: 'actions', label: '操作', align: 'right' },
]
const rows = computed(() => catalog.value.items.map(row => ({ ...row,
  start_date: row.start_date || '—', end_date: row.end_date || '—',
})))
async function load(page = catalog.value.page) {
  const request = ++listRequest
  loading.value = true
  error.value = ''
  try {
    const response = await localMarketList({ q: query.value, scope: scope.value, page, page_size: 20 })
    if (request !== listRequest) return
    catalog.value = response
    loaded.value = true
  } catch (e) {
    if (request === listRequest) error.value = e.message || '读取本地行情失败'
  } finally {
    if (request === listRequest) loading.value = false
  }
}
function search() {
  query.value = searchText.value.trim()
  closeDetail()
  load(1)
}
function changeScope(value) {
  scope.value = value
  closeDetail()
  load(1)
}
async function addStock(row) {
  if (addingSymbol.value) return
  addingSymbol.value = row.symbol
  try {
    await universeAdd([row.symbol])
    props.notify(`已将 ${row.name} 加入股票池`)
    await load()
    emit('changed')
  } catch (e) { props.notify(e.message || '加入股票池失败') }
  finally { addingSymbol.value = '' }
}

const selected = ref(null)
const detailPanel = ref(null)
const detail = ref(null)
const detailLoading = ref(false)
const detailError = ref('')
const showUpdate = ref(false)
const updating = ref(false)
const updateMessage = ref('')
const updateError = ref('')
const startDate = ref('')
const endDate = ref('')
let detailRequest = 0
function dateString(day) {
  return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`
}
async function readDetail() {
  const symbol = selected.value?.symbol
  if (!symbol) return
  const request = ++detailRequest
  detailLoading.value = true
  detailError.value = ''
  detail.value = null
  try {
    const response = await localMarketDetail(symbol)
    if (request === detailRequest) detail.value = response
  } catch (e) {
    if (request === detailRequest) detailError.value = e.message || '读取详情失败'
  } finally {
    if (request === detailRequest) detailLoading.value = false
  }
}
async function openDetail(row, update = false) {
  if (updating.value) return
  selected.value = row
  showUpdate.value = update
  updateMessage.value = ''
  updateError.value = ''
  const today = new Date()
  const start = row.end_date && row.end_date !== '—' ? new Date(`${row.end_date}T12:00:00`) : new Date(today)
  start.setDate(start.getDate() - (row.rows ? 7 : 365))
  startDate.value = dateString(start > today ? today : start)
  endDate.value = dateString(today)
  readDetail()
  await nextTick()
  detailPanel.value?.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
}
function closeDetail() {
  if (updating.value) return
  ++detailRequest
  selected.value = null
  detail.value = null
}
async function updateStock() {
  if (updating.value || !selected.value) return
  updateMessage.value = ''
  updateError.value = ''
  if (!startDate.value || !endDate.value || startDate.value > endDate.value || endDate.value > dateString(new Date())) {
    updateError.value = '请检查起止日期，结束日期不能晚于今天'
    return
  }
  updating.value = true
  try {
    const response = await updateLocalStock(selected.value.symbol, { start_date: startDate.value, end_date: endDate.value })
    if (response.status !== 'SUCCESS') throw new Error(response.message || '行情更新未成功，请重试')
    updateMessage.value = `更新完成：${response.message || '已同步所选日期区间的行情'}`
    await Promise.all([load(), readDetail()])
    emit('changed')
  } catch (e) { updateError.value = e.message || '更新行情失败' }
  finally { updating.value = false }
}
onActivated(() => load())
</script>

<template>
  <SectionCard title="本地行情查询" hint="查询本地已下载的股票，确认行情范围后再开始研究">
    <template #actions><button type="button" class="text-sm text-indigo-300 hover:underline disabled:opacity-50" :disabled="loading" @click="load()">刷新列表</button></template>
    <div class="flex flex-wrap gap-2" role="group" aria-label="行情查询范围">
      <button v-for="item in [{ key: 'all', label: '全部已下载', count: catalog.downloaded_count }, { key: 'universe', label: '当前股票池', count: catalog.universe_count }]" :key="item.key"
        type="button" :aria-pressed="scope === item.key" class="rounded-full border px-4 py-2 text-sm transition"
        :class="scope === item.key ? 'border-indigo-400/40 bg-indigo-500/20 text-indigo-200' : 'border-white/10 bg-white/5 text-slate-300 hover:bg-white/10'"
        @click="changeScope(item.key)">{{ item.label }}{{ loaded ? `（${item.count}）` : '' }}</button>
    </div>
    <form class="mt-4 flex flex-wrap items-center gap-3" @submit.prevent="search">
      <input v-model="searchText" aria-label="搜索本地行情" placeholder="输入股票名称或代码" maxlength="80" class="w-full max-w-sm rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
      <button type="submit" class="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-300 transition hover:bg-white/10">搜索</button>
    </form>
    <p class="mt-3 text-xs text-slate-400">“已保存区间完整”只表示区间内的交易日记录齐全；请结合截至日期判断是否需要更新。</p>
    <p v-if="scope === 'universe' && loaded" class="mt-2 text-xs text-slate-400">股票池 {{ catalog.universe_count }} 只，已有行情 {{ catalog.universe_downloaded_count }} 只，未下载 {{ catalog.universe_count - catalog.universe_downloaded_count }} 只。</p>
    <p v-if="loading" class="mt-4 text-sm text-slate-400" role="status">正在读取本地行情…</p>
    <p v-else-if="error" class="mt-4 text-sm text-rose-300" role="alert">{{ error }} <button type="button" class="underline" @click="load()">重试</button></p>
    <div v-else class="mt-4">
      <DataTable :columns="columns" :rows="rows" :empty="query ? '没有找到匹配的股票，请调整名称或代码' : scope === 'all' ? '本地暂无已下载行情，请先到数据更新下载股票池行情' : '当前股票池为空，请先到股票池管理添加股票'">
        <template #cell-name="{ row }"><span class="whitespace-nowrap">{{ row.name }}</span></template>
        <template #cell-symbol="{ row }"><span class="whitespace-nowrap">{{ row.symbol }}</span></template>
        <template #cell-start_date="{ row }"><span class="whitespace-nowrap">{{ row.start_date }}</span></template>
        <template #cell-end_date="{ row }"><span class="whitespace-nowrap">{{ row.end_date }}</span></template>
        <template #cell-status="{ row }"><span class="whitespace-nowrap text-xs" :class="row.status === 'COMPLETE' ? 'text-emerald-300' : row.status === 'NO_DATA' ? 'text-slate-400' : 'text-amber-300'">{{ row.status_label }}</span></template>
        <template #cell-actions="{ row }">
          <div class="flex items-center justify-end gap-3 whitespace-nowrap">
            <button type="button" class="text-indigo-300 hover:underline disabled:opacity-50" :disabled="updating" @click="openDetail(row)">详情</button>
            <button type="button" class="text-indigo-300 hover:underline disabled:opacity-50" :disabled="updating" @click="openDetail(row, true)">更新行情</button>
            <span v-if="row.in_universe" class="text-xs text-slate-500">已在股票池</span>
            <button v-else type="button" class="text-indigo-300 hover:underline disabled:opacity-50" :disabled="!!addingSymbol" @click="addStock(row)">{{ addingSymbol === row.symbol ? '加入中…' : '加入股票池' }}</button>
          </div>
        </template>
      </DataTable>
      <p v-if="rows.length" class="mt-2 text-xs text-slate-500 sm:hidden">左右滑动表格可查看完整信息与操作。</p>
      <div class="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-400">
        <span>共 {{ catalog.total }} 只 · 第 {{ catalog.page }} / {{ catalog.pages }} 页 · 每页 20 只</span>
        <div class="flex gap-2">
          <button type="button" class="rounded-lg border border-white/10 px-3 py-1.5 transition hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40" :disabled="catalog.page <= 1" @click="load(catalog.page - 1)">上一页</button>
          <button type="button" class="rounded-lg border border-white/10 px-3 py-1.5 transition hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40" :disabled="catalog.page >= catalog.pages" @click="load(catalog.page + 1)">下一页</button>
        </div>
      </div>
    </div>
    <section v-if="selected" ref="detailPanel" class="mt-5 scroll-mt-24 rounded-xl border border-white/10 bg-white/5 p-4" aria-label="单只股票行情详情">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <h3 class="text-lg font-semibold text-white">{{ selected.name }} · {{ selected.symbol }}</h3>
        <button type="button" class="text-sm text-slate-400 hover:text-white disabled:opacity-40" :disabled="updating" @click="closeDetail">关闭详情</button>
      </div>
      <p v-if="detailLoading" class="mt-3 text-sm text-slate-400">正在核对该股票的行情…</p>
      <p v-else-if="detailError" class="mt-3 text-sm text-rose-300">{{ detailError }} <button type="button" class="underline" @click="readDetail">重试</button></p>
      <div v-else-if="detail" class="mt-3 space-y-3 text-sm text-slate-300">
        <p>行情区间：{{ detail.start_date || '—' }} 至 {{ detail.end_date || '—' }} · 记录数：{{ detail.rows.toLocaleString() }}</p>
        <p>区间记录覆盖率：{{ detail.coverage == null ? '暂不能核对' : `${(detail.coverage * 100).toFixed(2)}%` }} · 缺失交易日：{{ detail.missing_rows ?? '待核对' }} · 未知状态：{{ detail.unknown_rows }} · 重复记录：{{ detail.duplicate_rows }}</p>
        <p v-if="detail.unexpected_rows" class="text-amber-300">有 {{ detail.unexpected_rows }} 条记录日期不在本地交易日历中，请核对行情与日历。</p>
        <p v-if="detail.status === 'NO_DATA'" class="text-amber-300">尚未下载行情，可选择日期区间后更新。</p>
        <p v-else-if="detail.coverage == null" class="text-amber-300">本地交易日历不足，暂时无法判断区间完整性。</p>
        <ul v-if="detail.missing_ranges.length" class="space-y-1 text-amber-300">
          <li v-for="range in detail.missing_ranges" :key="range.start_date">缺失：{{ range.start_date }} 至 {{ range.end_date }}（{{ range.days }} 个交易日）</li>
        </ul>
        <p v-if="detail.missing_range_count > 20" class="text-xs text-slate-400">共 {{ detail.missing_range_count }} 段缺失，以上显示前 20 段；可按完整区间重新更新。</p>
      </div>
      <button v-if="!showUpdate" type="button" class="mt-4 text-sm text-indigo-300 hover:underline" @click="showUpdate = true">选择日期并更新行情</button>
      <form v-if="showUpdate" class="mt-4 border-t border-white/10 pt-4" @submit.prevent="updateStock">
        <p class="mb-3 text-xs text-slate-400">仅更新 {{ selected.name }} 的行情，不改变股票池。{{ selected.rows ? '默认从已有行情末尾前 7 天补到今天' : '默认下载近一年行情' }}；补齐历史缺口时请调整开始日期。</p>
        <div class="grid gap-4 sm:grid-cols-2">
          <FormField label="更新开始日期" type="date" v-model="startDate" :disabled="updating" />
          <FormField label="更新结束日期" type="date" v-model="endDate" :disabled="updating" />
        </div>
        <button type="submit" :disabled="updating" class="mt-4 rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white transition hover:-translate-y-0.5 disabled:opacity-50">{{ updating ? '更新中…' : '开始更新该股票' }}</button>
        <p v-if="updating" class="mt-3 text-sm text-slate-400" role="status">正在更新，请保持页面打开。</p>
        <p v-if="updateMessage" class="mt-3 text-sm text-emerald-300" role="status">{{ updateMessage }}</p>
        <p v-if="updateError" class="mt-3 text-sm text-rose-300" role="alert">{{ updateError }}</p>
      </form>
    </section>
  </SectionCard>
</template>
