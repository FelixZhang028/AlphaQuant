<script setup>
import { computed, onActivated, ref } from 'vue'
import { openResearch } from '../researchNavigation.js'
import { listRuns, compareRuns } from '../../api.js'
import { MAX_COMPARED, recordsSummary, runTime, toggleSelection } from '../runRecords.js'
import SectionCard from '../ui/SectionCard.vue'
import DataTable from '../ui/DataTable.vue'
import LineChart from '../ui/LineChart.vue'
import StatusPill from '../ui/StatusPill.vue'
import EmptyState from '../ui/EmptyState.vue'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

// ---------- 回测记录 ----------
const runs = ref([])
const total = ref(0)
const stats = ref(null)
const loading = ref(false)
const error = ref('')
const keyword = ref('')

const summary = computed(() => recordsSummary(total.value, stats.value))

const runKindLabel = {
  single: '单次',
  optimize: '参数优化',
  walk_forward: '滚动验证',
  experiment: '实验',
  manual: '手动',
  unknown: '未记录',
}

function trustInfo(r) {
  if (r.legacy_unverified) return { text: '旧版未验证', cls: 'text-amber-300 bg-amber-400/10 border-amber-400/30' }
  if (r.validity_status === 'INVALID' || r.metrics_reliable === false) return { text: '不可用', cls: 'text-rose-300 bg-rose-400/10 border-rose-400/30' }
  if (r.validity_status === 'WARNING') return { text: '需复核', cls: 'text-amber-300 bg-amber-400/10 border-amber-400/30' }
  if (r.metrics_reliable) return { text: '审计通过', cls: 'text-emerald-300 bg-emerald-400/10 border-emerald-400/30' }
  return { text: '待验证', cls: 'text-rose-300 bg-rose-400/10 border-rose-400/30' }
}

function fmtPct(v) {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  if (Number.isNaN(n)) return '—'
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`
}

function fmtDd(v) {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  if (Number.isNaN(n)) return '—'
  return `${n.toFixed(2)}%`
}

function fmtRatio(v) {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  return Number.isNaN(n) ? '—' : n.toFixed(2)
}

function pctClass(v) {
  const n = Number(v)
  if (Number.isNaN(n)) return ''
  return n >= 0 ? 'text-emerald-300' : 'text-rose-300'
}

async function loadRuns(kw = '') {
  loading.value = true
  error.value = ''
  try {
    const data = await listRuns(kw ? { keyword: kw } : {})
    runs.value = data?.items || []
    total.value = data?.total ?? runs.value.length
    stats.value = data?.stats || null
    // 搜索后不在列表里的记录不再保持勾选。
    selectedIds.value = selectedIds.value.filter((id) => runs.value.some((r) => r.run_id === id))
  } catch (e) {
    error.value = e.message || '加载失败'
    props.notify(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function onSearch() {
  loadRuns(keyword.value.trim())
}

function onReset() {
  keyword.value = ''
  loadRuns('')
}

// ---------- 结果对比 ----------
const selectedIds = ref([])
const comparing = ref(false)
const comparison = ref(null)
const comparisonNote = ref('')
const comparisonScope = ref(null)
const navPoints = ref([])
const compareRunIds = ref([])
const palette = ['#818cf8', '#34d399', '#fbbf24', '#f472b6', '#22d3ee']

const runMap = computed(() => Object.fromEntries(runs.value.map((r) => [r.run_id, r])))
const selectedCount = computed(() => selectedIds.value.length)

function toggleSelect(runId) {
  const next = toggleSelection(selectedIds.value, runId)
  if (next === null) return props.notify(`最多选择 ${MAX_COMPARED} 次回测`)
  selectedIds.value = next
}

async function onCompare() {
  const ids = [...selectedIds.value]
  if (ids.length < 2) return props.notify('请至少选择 2 次回测进行对比')
  comparing.value = true
  comparison.value = null
  navPoints.value = []
  try {
    const data = await compareRuns(ids)
    comparison.value = data?.comparison || []
    comparisonNote.value = data.note
    comparisonScope.value = data.chart_scope
    navPoints.value = data?.normalized_nav || []
    compareRunIds.value = ids
  } catch (e) {
    props.notify(e.message || '对比失败')
  } finally {
    comparing.value = false
  }
}

const chartSeries = computed(() => {
  if (!navPoints.value.length) return []
  return compareRunIds.value.map((rid, i) => ({
    label: runMap.value[rid]?.strategy || rid,
    color: palette[i % palette.length],
    points: navPoints.value.map((p) => p[rid]),
  }))
})

const comparisonRows = computed(() => {
  if (!comparison.value) return []
  return comparison.value.map((c) => ({
    ...c,
    strategy: c.strategy || '—',
  }))
})

// ---------- 表格列 ----------
const showDetailedColumns = ref(false)
const selectColumn = { key: 'select', label: '对比' }
const fullRunColumns = [
  selectColumn,
  { key: 'run_id', label: '运行' },
  { key: 'run_kind', label: '类型' },
  { key: 'status', label: '状态' },
  { key: 'trust', label: '指标' },
  { key: 'grade', label: '可信度评级' },
  { key: 'strategy', label: '策略' },
  { key: 'start_date', label: '开始' },
  { key: 'end_date', label: '结束' },
  { key: 'cumulative_return', label: '累计收益', align: 'right' },
  { key: 'max_drawdown', label: '最大回撤', align: 'right' },
  { key: 'sharpe', label: '夏普', align: 'right' },
  { key: 'updated_at', label: '更新时间' },
  { key: 'actions', label: '操作' },
]
const runColumns = computed(() => showDetailedColumns.value ? fullRunColumns : [
  selectColumn,
  { key: 'strategy', label: '策略 / 记录' },
  { key: 'period', label: '回测区间' },
  { key: 'cumulative_return', label: '累计收益', align: 'right' },
  { key: 'max_drawdown', label: '最大回撤', align: 'right' },
  { key: 'sharpe', label: '夏普', align: 'right' },
  { key: 'trust', label: '指标状态' },
  { key: 'actions', label: '操作' },
])

const compareColumns = [
  { key: 'run_id', label: '运行' },
  { key: 'strategy', label: '策略' },
  { key: 'cumulative_return', label: '累计收益', align: 'right' },
  { key: 'max_drawdown', label: '最大回撤', align: 'right' },
  { key: 'sharpe', label: '夏普', align: 'right' },
  { key: 'sortino', label: '索提诺', align: 'right' },
  { key: 'calmar', label: '卡玛', align: 'right' },
  { key: 'metrics_reliable', label: '可信度' },
]

onActivated(() => loadRuns(keyword.value.trim()))
</script>

<template>
  <div class="space-y-6">
    <!-- 标题 -->
    <div class="glass glass-sheen rounded-2xl p-6">
      <h1 class="text-xl font-bold text-white">研究记录</h1>
      <p class="mt-1 text-sm text-slate-400">每一次回测都保存在这里：重新打开结果、带入配置继续研究，或勾选 2~5 次做对比。</p>
    </div>

    <!-- 回测记录：搜索、勾选对比、打开结果都在这一张表里 -->
    <SectionCard title="回测记录" :hint="summary">
      <template #actions>
        <span class="text-xs text-slate-500">已选 {{ selectedCount }} / {{ MAX_COMPARED }}</span>
        <button
          @click="onCompare"
          :disabled="comparing || selectedCount < 2"
          class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
        >
          {{ comparing ? '对比中…' : '对比所选' }}
        </button>
      </template>
      <div class="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <input
          v-model="keyword"
          @keyup.enter="onSearch"
          placeholder="按策略名、日期搜索…"
          aria-label="搜索回测记录"
          class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40 sm:max-w-sm"
        />
        <div class="flex items-center gap-2">
          <button @click="onSearch" :disabled="loading" class="rounded-full border border-white/10 px-4 py-2 text-sm text-slate-300 transition hover:bg-white/5 disabled:opacity-70">
            {{ loading ? '搜索中…' : '搜索' }}
          </button>
          <button v-if="keyword" @click="onReset" class="px-2 py-2 text-sm text-slate-400 hover:text-slate-200">清除</button>
        </div>
        <label class="flex items-center gap-2 text-sm text-slate-400 sm:ml-auto"><input v-model="showDetailedColumns" type="checkbox" class="accent-indigo-500" />显示详细字段</label>
      </div>
      <p v-if="error" class="mb-3 text-sm text-rose-300">{{ error }}</p>
      <div v-if="loading" class="text-sm text-slate-400">加载中…</div>
      <EmptyState v-else-if="!runs.length" :text="keyword ? '没有符合条件的回测记录' : '暂无回测记录'" />
      <DataTable v-else :columns="runColumns" :rows="runs" empty="暂无回测记录">
        <template #cell-select="{ row }">
          <input type="checkbox" class="h-4 w-4 rounded accent-indigo-500" :aria-label="`选择 ${row.run_id} 参加对比`"
            :checked="selectedIds.includes(row.run_id)" @change="toggleSelect(row.run_id)" />
        </template>
        <template #cell-actions="{ row }">
          <div class="flex flex-wrap gap-2 whitespace-nowrap text-sm text-indigo-300">
            <button @click="openResearch('backtest-review', { run: row.backtest_id || row.run_id })">查看结果</button>
            <button v-if="row.strategy_reference" @click="openResearch('backtest-review', { strategy: row.strategy_reference, run: row.backtest_id || row.run_id, mode: 'reuse' })">继续研究</button>
            <button v-if="row.strategy_reference?.startsWith('package:') || row.strategy_reference?.startsWith('user:')" @click="openResearch('strategy-hub', { strategy: row.strategy_reference })">回到策略</button>
          </div>
        </template>
        <template #cell-run_id="{ row }">
          <span class="font-mono text-xs text-indigo-300">{{ row.run_id }}</span>
        </template>
        <template #cell-run_kind="{ row }">
          <span class="text-slate-400">{{ runKindLabel[row.run_kind] || row.run_kind || '—' }}</span>
        </template>
        <template #cell-status="{ row }">
          <StatusPill :value="row.status" />
        </template>
        <template #cell-trust="{ row }">
          <span class="inline-flex rounded-full border px-2.5 py-0.5 text-xs whitespace-nowrap" :class="trustInfo(row).cls">
            {{ trustInfo(row).text }}
          </span>
        </template>
        <template #cell-grade="{ row }">
          <StatusPill :value="row.grade || '待检查'" :text="row.grade ? `评级 ${row.grade}` : '待检查'" />
        </template>
        <template #cell-strategy="{ row }">
          <span class="font-medium text-white">{{ row.strategy || '—' }}</span>
          <span v-if="!showDetailedColumns" class="mt-1 block text-xs text-slate-400">{{ row.run_id }} · {{ runTime(row.updated_at) }}</span>
        </template>
        <template #cell-period="{ row }"><span class="whitespace-nowrap text-slate-400">{{ row.start_date }}<br />至 {{ row.end_date }}</span></template>
        <template #cell-start_date="{ row }">
          <span class="text-slate-400">{{ row.start_date || '—' }}</span>
        </template>
        <template #cell-end_date="{ row }">
          <span class="text-slate-400">{{ row.end_date || '—' }}</span>
        </template>
        <template #cell-cumulative_return="{ row }">
          <span class="font-semibold" :class="pctClass(row.cumulative_return)">{{ fmtPct(row.cumulative_return) }}</span>
        </template>
        <template #cell-max_drawdown="{ row }">
          <span class="font-medium text-rose-300">{{ fmtDd(row.max_drawdown) }}</span>
        </template>
        <template #cell-sharpe="{ row }">
          <span class="text-slate-300">{{ fmtRatio(row.sharpe) }}</span>
        </template>
        <template #cell-updated_at="{ row }">
          <span class="whitespace-nowrap text-slate-400">{{ runTime(row.updated_at) }}</span>
        </template>
      </DataTable>
    </SectionCard>

    <!-- 对比结果 -->
    <SectionCard v-if="comparison && comparison.length" title="对比结果" hint="所选回测的净值与绩效指标。">
      <div class="space-y-6">
        <div>
          <div class="flex items-center justify-between text-xs text-slate-400">
            <span>净值对比 · {{ comparisonScope?.start_date }} 至 {{ comparisonScope?.end_date }}</span>
            <span class="text-slate-500">{{ comparison.length }} 次回测</span>
          </div>
          <div class="mt-2">
            <LineChart :series="chartSeries" :height="180" />
          </div>
          <div class="mt-3 flex flex-wrap gap-x-4 gap-y-2">
            <div v-for="(s, i) in chartSeries" :key="i" class="flex items-center gap-1.5 text-xs text-slate-400">
              <span class="h-2 w-2 rounded-full" :style="{ background: s.color }"></span>
              <span class="text-slate-300">{{ s.label }}</span>
              <span class="font-mono text-slate-500">{{ compareRunIds[i] }}</span>
            </div>
          </div>
        </div>

        <p class="text-xs text-slate-400">{{ comparisonNote }}</p>
        <DataTable :columns="compareColumns" :rows="comparisonRows" empty="暂无对比结果">
          <template #cell-run_id="{ row }">
            <span class="font-mono text-xs text-indigo-300">{{ row.run_id }}</span>
          </template>
          <template #cell-strategy="{ row }">
            <span class="font-medium text-white">{{ row.strategy }}</span>
          </template>
          <template #cell-cumulative_return="{ row }">
            <span class="font-semibold" :class="pctClass(row.cumulative_return)">{{ fmtPct(row.cumulative_return) }}</span>
          </template>
          <template #cell-max_drawdown="{ row }">
            <span class="font-medium text-rose-300">{{ fmtDd(row.max_drawdown) }}</span>
          </template>
          <template #cell-sharpe="{ row }">
            <span class="text-slate-300">{{ fmtRatio(row.sharpe) }}</span>
          </template>
          <template #cell-sortino="{ row }">
            <span class="text-slate-300">{{ fmtRatio(row.sortino) }}</span>
          </template>
          <template #cell-calmar="{ row }">
            <span class="text-slate-300">{{ fmtRatio(row.calmar) }}</span>
          </template>
          <template #cell-metrics_reliable="{ row }">
            <span class="inline-flex rounded-full border px-2.5 py-0.5 text-xs" :class="trustInfo(row).cls">{{ trustInfo(row).text }}</span>
          </template>
        </DataTable>
      </div>
    </SectionCard>
  </div>
</template>
