<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { getUniverse, universeAdd, universeRemove, universeSaveFilters, universeSearch } from '../../api.js'
import MetricCard from '../ui/MetricCard.vue'
import SectionCard from '../ui/SectionCard.vue'
import DataTable from '../ui/DataTable.vue'
import FormField from '../ui/FormField.vue'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

const loading = ref(false)
const universe = ref({ symbols: [], filters: {}, description: [] })

// ---------- 过滤设置表单（与后端 filters 结构对齐） ----------
const filters = reactive({
  exclude_st: false,
  exclude_suspended: false,
  minimum_listing_days: 0,
  minimum_history_days: 0,
  minimum_average_amount: 0,
})

async function load() {
  loading.value = true
  try {
    const data = await getUniverse()
    universe.value = data
    const f = data.filters || {}
    filters.exclude_st = !!f.exclude_st
    filters.exclude_suspended = !!f.exclude_suspended
    filters.minimum_listing_days = f.minimum_listing_days ?? 0
    filters.minimum_history_days = f.minimum_history_days ?? 0
    filters.minimum_average_amount = f.minimum_average_amount ?? 0
  } catch (e) {
    props.notify(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

// ---------- 指标卡片 ----------
const metrics = computed(() => {
  const desc = universe.value.description || []
  const withLocal = desc.filter((d) => (d.local_rows || 0) > 0).length
  const withoutLocal = desc.filter((d) => (d.local_rows || 0) === 0).length
  return [
    { label: '股票数量', value: (universe.value.symbols || []).length, sub: '当前股票池', tone: 'text-indigo-300' },
    { label: '已有本地行情', value: withLocal, sub: 'local_rows > 0', tone: 'text-emerald-300' },
    { label: '尚未下载行情', value: withoutLocal, sub: '待数据更新', tone: 'text-amber-300' },
  ]
})

// ---------- 当前股票池表格 ----------
const tableCols = [
  { key: 'symbol', label: '代码' },
  { key: 'name', label: '名称' },
  { key: 'local_rows', label: '本地记录数', align: 'right' },
  { key: 'start_date', label: '开始日期' },
  { key: 'end_date', label: '结束日期' },
]

const tableRows = computed(() =>
  (universe.value.description || []).map((d) => ({
    symbol: d.symbol,
    name: d.name || '—',
    local_rows: d.local_rows ?? 0,
    start_date: d.start_date || '—',
    end_date: d.end_date || '—',
  }))
)

const nameMap = computed(() => {
  const m = {}
  for (const d of universe.value.description || []) m[d.symbol] = d.name
  return m
})

// ---------- 添加股票（多代码文本） ----------
const addText = ref('')
const adding = ref(false)

// 按换行/逗号/空格拆分，去空、去重、支持 600519.SH -> 600519 去后缀
function parseSymbols(text) {
  const tokens = String(text || '')
    .split(/[\s,，;；、\r\n]+/)
    .map((t) => t.trim())
    .filter(Boolean)
  const seen = new Set()
  const out = []
  for (let t of tokens) {
    let s = t.toUpperCase()
    s = s.replace(/\.(SH|SZ|BJ)$/, '')
    s = s.replace(/^(SH|SZ|BJ)(\d{6})$/, '$2')
    if (s && !seen.has(s)) {
      seen.add(s)
      out.push(s)
    }
  }
  return out
}

async function doAdd(symbols) {
  adding.value = true
  try {
    const res = await universeAdd(symbols)
    props.notify(`已添加 ${res.count} 只股票`)
    await load()
    return true
  } catch (e) {
    props.notify(e.message || '添加失败')
    return false
  } finally {
    adding.value = false
  }
}

async function addCodes() {
  const symbols = parseSymbols(addText.value)
  if (!symbols.length) return props.notify('请输入股票代码')
  if (await doAdd(symbols)) addText.value = ''
}

// ---------- 按名称搜索 ----------
const searchQ = ref('')
const searching = ref(false)
const searchResults = ref([])
const selectedSearch = ref([])

function toggleSearch(symbol) {
  const i = selectedSearch.value.indexOf(symbol)
  if (i >= 0) selectedSearch.value.splice(i, 1)
  else selectedSearch.value.push(symbol)
}

async function onSearch() {
  const q = searchQ.value.trim()
  if (!q) return props.notify('请输入搜索关键词')
  searching.value = true
  try {
    const data = await universeSearch(q)
    searchResults.value = data.results || []
    selectedSearch.value = []
  } catch (e) {
    props.notify(e.message || '搜索失败')
  } finally {
    searching.value = false
  }
}

async function addSelectedSearch() {
  if (!selectedSearch.value.length) return props.notify('请先选择要添加的股票')
  if (await doAdd(selectedSearch.value)) {
    selectedSearch.value = []
    searchResults.value = []
    searchQ.value = ''
  }
}

// ---------- 移除股票 ----------
const selectedRemove = ref([])
const confirmRemove = ref(false)
const removing = ref(false)

function toggleRemove(symbol) {
  const i = selectedRemove.value.indexOf(symbol)
  if (i >= 0) selectedRemove.value.splice(i, 1)
  else selectedRemove.value.push(symbol)
}

async function removeSelected() {
  if (!selectedRemove.value.length) return props.notify('请先选择要移除的股票')
  if (!confirmRemove.value) return props.notify('请先勾选确认移除')
  if (!confirm(`确定从股票池移除 ${selectedRemove.value.length} 只股票？`)) return
  removing.value = true
  try {
    const res = await universeRemove(selectedRemove.value)
    props.notify(`已移除 ${res.count} 只股票`)
    selectedRemove.value = []
    confirmRemove.value = false
    await load()
  } catch (e) {
    props.notify(e.message || '移除失败')
  } finally {
    removing.value = false
  }
}

// ---------- 过滤设置 ----------
const savingFilters = ref(false)

async function saveFilters() {
  savingFilters.value = true
  try {
    await universeSaveFilters({
      exclude_st: !!filters.exclude_st,
      exclude_suspended: !!filters.exclude_suspended,
      minimum_listing_days: Number(filters.minimum_listing_days) || 0,
      minimum_history_days: Number(filters.minimum_history_days) || 0,
      minimum_average_amount: Number(filters.minimum_average_amount) || 0,
    })
    props.notify('过滤设置已保存')
  } catch (e) {
    props.notify(e.message || '保存失败')
  } finally {
    savingFilters.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-6">
    <!-- 标题 -->
    <div class="glass glass-sheen relative overflow-hidden rounded-2xl p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-indigo-500/20 blur-3xl" />
      <h1 class="text-xl font-bold text-white">股票池管理</h1>
      <p class="mt-1 text-sm text-slate-400">添加、搜索或移除股票，数据更新和回测自动使用当前股票池</p>
    </div>

    <!-- 指标 -->
    <section class="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
      <MetricCard
        v-for="m in metrics"
        :key="m.label"
        :label="m.label"
        :value="m.value"
        :sub="m.sub"
        :tone="m.tone"
      />
    </section>

    <!-- 当前股票池 -->
    <SectionCard title="当前股票池" hint="回测与数据更新将使用以下股票">
      <div v-if="loading" class="text-sm text-slate-400">加载中…</div>
      <DataTable v-else :columns="tableCols" :rows="tableRows" empty="股票池为空，请添加股票" />
    </SectionCard>

    <!-- 添加股票 -->
    <SectionCard title="添加股票" hint="支持换行、逗号或空格分隔多个代码，如 600519.SH、000001.SZ">
      <label class="block">
        <span class="mb-1 block text-xs text-slate-400">股票代码</span>
        <textarea
          v-model="addText"
          rows="3"
          placeholder="例如：600519.SH, 000001.SZ 300750"
          class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40"
        />
      </label>
      <button
        @click="addCodes"
        :disabled="adding"
        class="mt-3 rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
      >
        {{ adding ? '添加中…' : '添加代码' }}
      </button>
    </SectionCard>

    <!-- 按名称搜索 -->
    <SectionCard title="按名称搜索" hint="通过股票名称模糊搜索，勾选后批量添加">
      <div class="flex flex-wrap items-center gap-3">
        <input
          v-model="searchQ"
          @keyup.enter="onSearch"
          placeholder="输入名称，如 贵州茅台"
          class="w-full max-w-sm rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40"
        />
        <button
          @click="onSearch"
          :disabled="searching"
          class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
        >
          {{ searching ? '搜索中…' : '搜索' }}
        </button>
      </div>

      <div v-if="searchResults.length" class="mt-4 space-y-1">
        <label
          v-for="r in searchResults"
          :key="r.symbol"
          class="flex cursor-pointer items-center gap-2.5 rounded-xl border border-white/5 bg-white/5 px-3 py-2 text-sm text-slate-300 transition hover:bg-white/10"
        >
          <input
            type="checkbox"
            :checked="selectedSearch.includes(r.symbol)"
            class="h-4 w-4 rounded border-white/20 bg-white/5 accent-indigo-500"
            @change="toggleSearch(r.symbol)"
          />
          <span class="font-mono text-xs text-indigo-300">{{ r.symbol }}</span>
          <span>{{ r.name }}</span>
        </label>
        <button
          @click="addSelectedSearch"
          :disabled="adding"
          class="mt-3 rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
        >
          添加选中的股票
        </button>
      </div>
      <p v-else-if="searchQ && !searching" class="mt-4 text-sm text-slate-500">输入关键词并点击「搜索」。</p>
    </SectionCard>

    <!-- 移除股票 -->
    <SectionCard title="移除股票" hint="勾选当前股票池中的股票，确认后移除">
      <div v-if="!universe.symbols.length" class="text-sm text-slate-500">当前股票池为空。</div>
      <div v-else class="grid gap-1 sm:grid-cols-2 xl:grid-cols-3">
        <label
          v-for="s in universe.symbols"
          :key="s"
          class="flex cursor-pointer items-center gap-2.5 rounded-xl border border-white/5 bg-white/5 px-3 py-2 text-sm text-slate-300 transition hover:bg-white/10"
        >
          <input
            type="checkbox"
            :checked="selectedRemove.includes(s)"
            class="h-4 w-4 rounded border-white/20 bg-white/5 accent-indigo-500"
            @change="toggleRemove(s)"
          />
          <span class="font-mono text-xs text-indigo-300">{{ s }}</span>
          <span v-if="nameMap[s]" class="truncate text-slate-400">{{ nameMap[s] }}</span>
        </label>
      </div>

      <label v-if="universe.symbols.length" class="mt-4 flex items-center gap-2.5">
        <input
          type="checkbox"
          v-model="confirmRemove"
          class="h-4 w-4 rounded border-white/20 bg-white/5 accent-indigo-500"
        />
        <span class="text-sm text-slate-300">我已确认要移除所选股票</span>
      </label>

      <button
        v-if="universe.symbols.length"
        @click="removeSelected"
        :disabled="removing"
        class="mt-3 rounded-full border border-rose-400/30 px-4 py-2 text-sm font-semibold text-rose-300 transition hover:bg-rose-400/10 disabled:opacity-70"
      >
        {{ removing ? '移除中…' : '移除选中的股票' }}
      </button>
    </SectionCard>

    <!-- 过滤设置 -->
    <SectionCard title="股票过滤设置" hint="以下条件将影响数据更新时的股票筛选">
      <div class="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        <label class="flex items-center gap-2.5 pt-6">
          <input
            type="checkbox"
            v-model="filters.exclude_st"
            class="h-4 w-4 rounded border-white/20 bg-white/5 accent-indigo-500"
          />
          <span class="text-sm text-slate-300">排除 ST</span>
        </label>
        <label class="flex items-center gap-2.5 pt-6">
          <input
            type="checkbox"
            v-model="filters.exclude_suspended"
            class="h-4 w-4 rounded border-white/20 bg-white/5 accent-indigo-500"
          />
          <span class="text-sm text-slate-300">排除停牌</span>
        </label>
        <FormField label="最少上市天数" type="number" v-model="filters.minimum_listing_days" min="0" />
        <FormField label="最少历史交易日" type="number" v-model="filters.minimum_history_days" min="0" />
        <FormField label="最低20日平均成交额" type="number" v-model="filters.minimum_average_amount" min="0" step="1" />
      </div>
      <button
        @click="saveFilters"
        :disabled="savingFilters"
        class="mt-5 rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
      >
        {{ savingFilters ? '保存中…' : '保存过滤设置' }}
      </button>
    </SectionCard>
  </div>
</template>
