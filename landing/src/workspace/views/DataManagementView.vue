<script setup>
import { computed, onMounted, ref } from 'vue'
import { dataOverview } from '../../api.js'
import MetricCard from '../ui/MetricCard.vue'
import SectionCard from '../ui/SectionCard.vue'
import DataTable from '../ui/DataTable.vue'
import StatusPill from '../ui/StatusPill.vue'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

// ---------- 概览 ----------
const overview = ref(null)
const loading = ref(false)

const metrics = computed(() => {
  const o = overview.value || {}
  return [
    {
      label: '证券主表',
      value: o.security_count != null ? Number(o.security_count).toLocaleString() : '—',
      sub: '全A证券基本信息',
    },
    {
      label: '配置股票',
      value: o.configured_symbol_count != null ? Number(o.configured_symbol_count).toLocaleString() : '—',
      sub: '股票池标的数量',
    },
    {
      label: '行情覆盖率',
      value: fmtCoverage(o.coverage_ratio),
      sub: '已配置标的覆盖',
      tone: 'text-emerald-300',
    },
    {
      label: '行情记录',
      value: o.market_rows != null ? Number(o.market_rows).toLocaleString() : '—',
      sub: '本地行情记录数',
    },
    {
      label: '未知状态记录',
      value: o.unknown_status_rows != null ? Number(o.unknown_status_rows).toLocaleString() : '—',
      sub: '待核对状态',
      tone: o.unknown_status_rows > 0 ? 'text-rose-300' : '',
    },
    {
      label: '最近行情来源',
      value: o.last_market_source ? providerLabel(o.last_market_source) : '—',
      sub: o.benchmark_symbol ? `基准 ${o.benchmark_symbol}` : '行情数据源',
      tone: 'text-indigo-300',
    },
  ]
})

// ---------- 行情数据源 ----------
const providers = computed(() => overview.value?.providers || [])
const providerLabel = (id) => {
  const hit = providers.value.find((p) => p.provider === id)
  return hit ? hit.display_name : id
}
const primaryProvider = computed(() => providers.value[0] || null)

const sourceCols = [
  { key: 'display_name', label: '数据源' },
  { key: 'role', label: '角色' },
  { key: 'readiness', label: '状态' },
  { key: 'detail', label: '说明' },
]
const roleLabels = { PRIMARY: '首选', FALLBACK: '备用' }
const sourceRows = computed(() =>
  providers.value.map((p) => ({
    display_name: p.display_name,
    role: roleLabels[p.role] || p.role,
    readiness: p.readiness,
    detail: p.detail,
    failed: p.readiness !== 'READY',
  }))
)

// ---------- 覆盖率 ----------
const coverageCols = [
  { key: 'symbol', label: '代码' },
  { key: 'coverage', label: '覆盖率', align: 'right' },
  { key: 'start_date', label: '开始日期' },
  { key: 'end_date', label: '结束日期' },
  { key: 'rows', label: '记录数', align: 'right' },
]

const coverageRows = computed(() =>
  (overview.value?.per_symbol || []).map((s) => ({
    symbol: s.symbol,
    coverage: fmtCoverage(s.coverage),
    start_date: s.start_date,
    end_date: s.end_date,
    rows: s.rows != null ? Number(s.rows).toLocaleString() : '—',
  }))
)

function fmtCoverage(v) {
  if (v == null) return '—'
  const n = Number(v)
  const pct = n > 1 ? n : n * 100
  return `${pct.toFixed(2)}%`
}

async function loadOverview() {
  loading.value = true
  try {
    overview.value = await dataOverview()
  } catch (e) {
    props.notify(e.message || '加载数据概览失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadOverview)
</script>

<template>
  <div class="space-y-6">
    <!-- 标题 -->
    <div class="glass relative overflow-hidden rounded-2xl p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-indigo-500/20 blur-3xl" />
      <h1 class="text-xl font-bold text-white">数据资产</h1>
      <p class="mt-1 text-sm text-slate-400">查看行情覆盖率、数据源状态与数据版本；增量更新与全市场回填请前往「数据更新」</p>
    </div>

    <!-- 指标 -->
    <section class="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard
        v-for="m in metrics"
        :key="m.label"
        :label="m.label"
        :value="m.value"
        :sub="m.sub"
        :tone="m.tone"
      />
    </section>

    <!-- 行情数据源（迁移自 AlphaQuant） -->
    <SectionCard title="行情数据源" hint="本机配置状态；实际成功来源以本次更新结果为准">
      <p
        v-if="primaryProvider"
        class="mb-4 rounded-xl px-3 py-2 text-sm"
        :class="primaryProvider.readiness === 'READY' ? 'bg-emerald-500/10 text-emerald-300' : 'bg-amber-500/10 text-amber-300'"
      >
        {{
          primaryProvider.readiness === 'READY'
            ? `首选数据源 ${primaryProvider.display_name} 已配置。`
            : `首选数据源 ${primaryProvider.display_name} 尚未就绪；更新行情时会自动尝试备用数据源。`
        }}
      </p>
      <DataTable :columns="sourceCols" :rows="sourceRows" empty="暂无已配置数据源">
        <template #cell-readiness="{ row }">
          <StatusPill :value="row.readiness === 'READY' ? 'SUCCESS' : 'FAILED'" :text="row.readiness === 'READY' ? '已就绪' : '未就绪'" />
        </template>
        <template #cell-detail="{ row }">
          <span :class="row.failed ? 'text-slate-400' : 'text-slate-300'">{{ row.detail }}</span>
        </template>
      </DataTable>
    </SectionCard>

    <!-- 覆盖率 -->
    <SectionCard title="覆盖率" hint="各配置标的的行情覆盖情况">
      <div v-if="loading && !overview" class="text-sm text-slate-400">加载中…</div>
      <DataTable v-else :columns="coverageCols" :rows="coverageRows" empty="暂无覆盖率数据" />
    </SectionCard>

    <!-- 数据版本说明 -->
    <SectionCard title="数据版本说明" hint="本地数据范围与版本记录">
      <p class="text-sm leading-relaxed text-slate-400">
        本地行情数据库按数据源顺序增量更新，每次更新生成一个数据版本（version_id），用于追踪数据快照与覆盖范围。
      </p>
      <ul class="mt-3 space-y-1.5 text-xs text-slate-500">
        <li>· 证券主表：全 A 股证券基本信息，按更新日期全量刷新。</li>
        <li>· 配置股票池行情：仅更新股票池内标的的日线行情，覆盖起止日期由开始/结束日期决定。</li>
        <li>· 基准指数：更新基准指数（默认 000300.SH）行情，用于净值对齐。</li>
        <li>· 覆盖率 = 已配置标的中具备完整行情记录的占比。</li>
      </ul>
    </SectionCard>
  </div>
</template>
