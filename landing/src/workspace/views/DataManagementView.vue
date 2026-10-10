<script setup>
import { computed, onActivated, ref } from 'vue'
import { dataOverview } from '../../api.js'
import { summarizeDataOverview } from '../dataPresentation.js'
import MetricCard from '../ui/MetricCard.vue'
import DataTable from '../ui/DataTable.vue'
import StatusPill from '../ui/StatusPill.vue'
import LocalMarketQuery from '../ui/LocalMarketQuery.vue'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

// ---------- 概览 ----------
const overview = ref(null)
const loading = ref(true)
const loadError = ref('')
const summary = computed(() => summarizeDataOverview(overview.value, { loading: loading.value, error: loadError.value }))
function navigate(key) {
  window.dispatchEvent(new CustomEvent('fq-navigate', { detail: key }))
}

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

function fmtCoverage(v) {
  if (v == null) return '—'
  const n = Number(v)
  const pct = n > 1 ? n : n * 100
  return `${pct.toFixed(2)}%`
}

async function loadOverview() {
  loading.value = true
  loadError.value = ''
  try {
    overview.value = await dataOverview()
  } catch (e) {
    loadError.value = e.message || '加载数据概览失败'
    props.notify(e.message || '加载数据概览失败')
  } finally {
    loading.value = false
  }
}

onActivated(loadOverview)
</script>

<template>
  <div class="space-y-6">
    <!-- 标题 -->
    <div class="glass relative overflow-hidden rounded-2xl p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-indigo-500/20 blur-3xl" />
      <h1 class="text-xl font-bold text-white">数据概览</h1>
      <p class="mt-1 text-sm text-slate-400">选好股票，更新行情，然后开始研究。</p>
      <ol class="mt-4 flex flex-wrap gap-3 text-sm text-slate-300" aria-label="数据准备步骤">
        <li><button type="button" class="glass glass-sheen preparation-step" @click="navigate('universe')">1. 选择股票</button></li>
        <li><button type="button" class="glass glass-sheen preparation-step" @click="navigate('data-update')">2. 更新数据</button></li>
        <li><button type="button" class="glass glass-sheen preparation-step" @click="navigate('backtest-review')">3. 开始研究</button></li>
      </ol>
    </div>

    <section class="glass rounded-2xl p-5" aria-labelledby="data-version-heading">
      <h2 id="data-version-heading" class="text-lg font-semibold text-white">数据详情与版本说明</h2>
      <section class="mt-4 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        <MetricCard v-for="m in metrics" :key="m.label" :label="m.label" :value="m.value" :sub="m.sub" :tone="m.tone" />
      </section>
      <p class="mt-4 text-sm leading-relaxed text-slate-400">
        本地行情数据库按数据源顺序增量更新，每次更新生成一个数据版本（version_id），用于追踪数据快照与覆盖范围。
      </p>
      <ul class="mt-3 space-y-1.5 text-xs text-slate-500">
        <li>· 证券主表：全 A 股证券基本信息，按更新日期全量刷新。</li>
        <li>· 配置股票池行情：仅更新股票池内标的的日线行情，覆盖起止日期由开始/结束日期决定。</li>
        <li>· 基准指数：更新基准指数（默认 000300.SH）行情，用于净值对齐。</li>
        <li>· 记录覆盖率按已保存日期区间的预期交易日计算，不表示行情已更新到最新交易日。</li>
      </ul>
    </section>

    <section class="glass rounded-2xl p-5" aria-live="polite" :aria-busy="loading">
      <h2 class="text-sm font-semibold text-white">{{ summary.title }}</h2>
      <p class="mt-2 max-w-3xl text-sm text-slate-400">{{ summary.hint }}</p>
      <p v-if="loadError" class="mt-2 text-sm text-rose-300">{{ loadError }}</p>
      <div class="mt-5 flex flex-wrap gap-3">
        <button v-if="loadError" type="button" class="rounded-full border border-white/10 px-5 py-2 text-sm text-slate-300" :disabled="loading" @click="loadOverview">重新读取</button>
        <button type="button" class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-5 py-2 text-sm font-semibold text-white" @click="navigate(summary.state === 'empty' ? 'universe' : 'data-update')">{{ summary.state === 'empty' ? '选择股票' : '更新数据' }}</button>
        <button type="button" class="rounded-full border border-white/10 px-5 py-2 text-sm text-slate-300 hover:bg-white/5" @click="navigate('universe')">查看股票池</button>
        <button v-if="summary.state === 'covered'" type="button" class="px-3 py-2 text-sm text-indigo-300 hover:underline" @click="navigate('backtest-review')">开始回测 →</button>
      </div>
    </section>

    <section class="grid gap-5 sm:grid-cols-3" aria-label="数据状态摘要">
      <MetricCard label="行情截至日期" :value="summary.through || '—'" sub="已有行情股票中最早的截止日期" />
      <MetricCard label="股票池覆盖" :value="summary.total == null ? '—' : `${summary.covered} / ${summary.total} 只`" :sub="summary.coverage == null ? '等待检查' : `已保存区间记录覆盖率 ${fmtCoverage(summary.coverage)}`" />
      <MetricCard label="待处理问题" :value="loading || loadError || summary.unknown == null ? '待检查' : summary.state === 'covered' ? '0 项' : '需要查看'" :sub="summary.missing == null || summary.unknown == null ? '等待检查' : `${summary.missing ? `${summary.missing} 只缺行情` : summary.coverage < 1 ? '部分交易日缺失' : '股票均有行情'} · ${summary.unknown} 条未知状态记录`" />
    </section>

    <LocalMarketQuery :notify="notify" @changed="loadOverview" />

    <details class="glass rounded-2xl p-5">
      <summary class="cursor-pointer text-lg font-semibold text-white">数据源与高级工具</summary>
      <div class="mt-4">
        <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
          <p class="max-w-2xl text-sm text-slate-400">日常更新会自动选择来源。XTick 的凭证配置与专项查询在这里进入。</p>
          <button type="button" class="rounded-full border border-white/10 px-4 py-2 text-sm text-indigo-300 hover:bg-white/5" @click="navigate('xtick-data')">打开 XTick 数据服务 →</button>
        </div>
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
        <p class="mt-3 text-xs text-slate-500">这里只展示本机配置状态；配置就绪不等于连接成功。XTick 专项查询目前不用于批量回测更新。</p>
      </div>
    </details>

  </div>
</template>

<style scoped>
.preparation-step {
  border-radius: 0.75rem;
  padding: 0.625rem 1rem;
  transition: transform 0.2s ease, border-color 0.2s ease, background-color 0.2s ease;
}
.preparation-step:hover {
  transform: translateY(-2px);
  border-color: rgba(129, 140, 248, 0.4);
}
.preparation-step:active {
  transform: translateY(0);
}
.preparation-step:focus-visible {
  outline: 2px solid #818cf8;
  outline-offset: 3px;
}
@media (prefers-reduced-motion: reduce) {
  .preparation-step { transition: none; }
  .preparation-step:hover { transform: none; }
  .preparation-step::after { transition: none; }
}
</style>
