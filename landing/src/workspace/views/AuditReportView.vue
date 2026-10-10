<script setup>
import { computed, onActivated, onMounted, ref, watch } from 'vue'
import { getRunAudit, listAuditRuns } from '../../api.js'
import MetricCard from '../ui/MetricCard.vue'
import SectionCard from '../ui/SectionCard.vue'
import DataTable from '../ui/DataTable.vue'
import FormField from '../ui/FormField.vue'
import StrategyForensicsView from './StrategyForensicsView.vue'
import { pendingAuditRun } from '../auditLink.js'

const props = defineProps({
  routeContext: { type: Object, default: () => ({}) },
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

// ---------- 审计对象切换：平台回测 / 外部材料 ----------
const mode = ref('平台回测')

// ---------- 记录选择 ----------
const runs = ref([])
const selectedRun = ref('')
const loading = ref(false)
const auditing = ref(false)
const report = ref(null)

// ---------- 评级视觉语言：A 绿 / B 蓝 / C 黄 / D 红 ----------
const GRADE_TONE = {
  A: 'text-emerald-300',
  B: 'text-sky-300',
  C: 'text-amber-300',
  D: 'text-rose-300',
}
const GRADE_BANNER = {
  A: 'bg-emerald-500/10 text-emerald-200 border-emerald-400/30',
  B: 'bg-sky-500/10 text-sky-200 border-sky-400/30',
  C: 'bg-amber-500/10 text-amber-200 border-amber-400/30',
  D: 'bg-rose-500/10 text-rose-200 border-rose-400/30',
}
const STATUS_LABELS = { pass: '通过', warn: '警告', fail: '不通过', unavailable: '无法评估', not_applicable: '不适用' }
const STATUS_TONE = {
  pass: 'text-emerald-300 bg-emerald-400/10 border-emerald-400/30',
  warn: 'text-amber-300 bg-amber-400/10 border-amber-400/30',
  fail: 'text-rose-300 bg-rose-400/10 border-rose-400/30',
  unavailable: 'text-amber-300 bg-amber-400/10 border-amber-400/30',
  not_applicable: 'text-slate-300 bg-white/5 border-white/10',
}
const SEVERITY_LABELS = { info: '信息', warn: '警告', fail: '不通过' }
const SEVERITY_TONE = { info: 'text-slate-400 border-white/10 bg-white/5', warn: 'text-amber-300 border-amber-400/30 bg-amber-400/10', fail: 'text-rose-300 border-rose-400/30 bg-rose-400/10' }

const runOptions = computed(() =>
  runs.value.map((r) => ({
    value: r.run_id,
    label: `${r.run_label}${r.metrics_reliable === false ? '（绩效不可用）' : ''}`,
  }))
)

// ---------- 评级仪表盘 ----------
const gradeTone = computed(() => GRADE_TONE[report.value?.grade] || 'text-white')

const metrics = computed(() => {
  const r = report.value
  if (!r) return []
  const dims = r.dimensions || []
  const passed = dims.filter((d) => d.status === 'pass').length
  const ratio =
    r.transaction_cost_ratio != null ? `${(Number(r.transaction_cost_ratio) * 100).toFixed(2)}%` : '—'
  return [
    { label: '可信度评级', value: r.grade, sub: '六维综合评级', tone: gradeTone.value },
    { label: '审计维度通过', value: `${passed}/${dims.length}`, sub: '数据/未来函数/偏差/成本/容量/搜索偏差' },
    {
      label: '绩效指标',
      value: r.metrics_reliable ? '可用' : '不可用',
      sub: '净值与收益指标可信度',
      tone: r.metrics_reliable ? 'text-emerald-300' : 'text-rose-300',
    },
    { label: '净值观测', value: `${Number(r.observations || 0).toLocaleString()}`, sub: '个交易日' },
    { label: '成本占初始资金', value: ratio, sub: '交易成本合计占比', tone: 'text-indigo-300' },
  ]
})

// ---------- 参数搜索偏差（第六维：DSR 选择偏差证据） ----------
const SELECTION_BANNER = {
  pass: 'bg-emerald-500/10 text-emerald-200 border-emerald-400/30',
  warn: 'bg-amber-500/10 text-amber-200 border-amber-400/30',
  unavailable: 'bg-amber-500/10 text-amber-200 border-amber-400/30',
  not_applicable: 'bg-white/5 text-slate-300 border-white/10',
}
const selection = computed(() => report.value?.selection_bias || null)

const selectionMetrics = computed(() => {
  const s = selection.value
  if (!s) return []
  return [
    { label: '本批尝试', value: s.trial_count != null ? String(s.trial_count) : '未知', sub: '网格搜索组合数' },
    { label: '可计算试验', value: String(s.valid_trials ?? '—'), sub: '具备完整收益数据' },
    { label: '估计独立试验', value: s.effective_trials != null ? String(s.effective_trials) : '—', sub: '按试验间相关性折算' },
    {
      label: 'DSR 显著性',
      value: s.dsr != null ? `${(Number(s.dsr) * 100).toFixed(1)}%` : '—',
      sub: '95% 为审计参考门槛',
      tone: s.dsr != null && Number(s.dsr) >= 0.95 ? 'text-emerald-300' : '',
    },
  ]
})

function fmtPct(v) {
  return v != null ? `${(Number(v) * 100).toFixed(1)}%` : '—'
}
function fmtNum(v) {
  return v != null ? Number(v).toFixed(3) : '—'
}
const OBJECTIVE_LABELS = { sharpe: '夏普比率', annual_return: '年化收益', calmar: '卡玛比率', max_drawdown: '最大回撤最小' }
const selectionBasisRows = computed(() => {
  const s = selection.value
  if (!s) return []
  return [
    { name: '所属实验', value: s.optimization_id || '未关联' },
    { name: '原排序指标', value: OBJECTIVE_LABELS[s.objective] || s.objective || '未知' },
    { name: '年化 Sharpe', value: fmtNum(s.observed_sharpe) },
    { name: '未校正显著性（PSR）', value: fmtPct(s.psr) },
    { name: '选择校正门槛（年化 Sharpe）', value: fmtNum(s.benchmark_sharpe) },
    { name: '试验平均相关性', value: fmtNum(s.average_correlation) },
    { name: '最佳与中位 Sharpe 差距（年化）', value: fmtNum(s.best_median_gap) },
    { name: '收益观测数', value: s.observations != null ? String(s.observations) : '—' },
  ]
})

const evidenceCols = [
  { key: 'run', label: '运行编号' },
  { key: 'status', label: '试验状态' },
  { key: 'usable', label: '可计算' },
  { key: 'sharpe', label: '年化 Sharpe' },
  { key: 'note', label: '说明' },
]
const evidenceRows = computed(() =>
  (selection.value?.evidence || []).map((row) => ({
    run: String(row['运行编号'] ?? '—'),
    status: String(row['试验状态'] ?? '—'),
    usable: row['可计算'] ? '是' : '否',
    sharpe: row['年化 Sharpe'] != null ? Number(row['年化 Sharpe']).toFixed(3) : '—',
    note: String(row['说明'] ?? ''),
  }))
)

// ---------- 五维审计总览 ----------
const dimensionCols = [
  { key: 'title', label: '审计维度' },
  { key: 'status', label: '结论' },
  { key: 'summary', label: '要点' },
]
const dimensionRows = computed(() =>
  (report.value?.dimensions || []).map((d) => ({
    title: d.title,
    status: d.status,
    summary: d.findings?.length ? d.findings[0].message : '—',
  }))
)

// ---------- 维度明细（折叠区） ----------
const expanded = ref({})
watch(report, (r) => {
  // 未通过的维度默认展开（与 AlphaQuant 交互一致）
  expanded.value = {}
  for (const d of r?.dimensions || []) expanded.value[d.key] = d.status !== 'pass'
})
function toggleDim(key) {
  expanded.value[key] = !expanded.value[key]
}

// ---------- 证据链 ----------
const issueCols = [
  { key: 'code', label: '问题代码' },
  { key: 'severity', label: '级别' },
  { key: 'message', label: '说明' },
]
const issueRows = computed(() =>
  (report.value?.issues || []).map((i) => ({
    code: String(i.code || ''),
    severity: String(i.severity || ''),
    message: String(i.message || ''),
  }))
)

// ---------- 审计假设 ----------
function fmtBool(v) {
  if (v === true) return '启用'
  if (v === false) return '停用'
  return '未记录'
}
const assumptionRows = computed(() => {
  const a = report.value?.assumptions || {}
  return [
    { name: '历史分期费率', value: fmtBool(a.historical_fees) },
    {
      name: '参与率上限',
      value: a.max_participation != null ? `${(Number(a.max_participation) * 100).toFixed(1)}%` : '未记录',
    },
    {
      name: '滑点率',
      value: a.slippage_rate != null ? `${(Number(a.slippage_rate) * 100).toFixed(3)}%` : '未记录',
    },
    { name: '未知状态策略', value: a.unknown_status_policy != null ? String(a.unknown_status_policy) : '未记录' },
  ]
})

// ---------- 数据加载 ----------
async function loadRuns() {
  loading.value = true
  try {
    const data = await listAuditRuns()
    runs.value = data.items || []
    if (runs.value.length && !selectedRun.value) selectedRun.value = runs.value[0].run_id
    // 深链指定的记录若不在列表中（明细缺失），回退到首条，避免选择框悬空。
    if (runs.value.length && !runs.value.some((r) => r.run_id === selectedRun.value)) {
      selectedRun.value = runs.value[0].run_id
    }
  } catch (e) {
    props.notify(e.message || '加载回测记录失败')
  } finally {
    loading.value = false
  }
}

async function loadAudit(runId) {
  if (!runId) {
    report.value = null
    return
  }
  auditing.value = true
  try {
    report.value = await getRunAudit(runId)
  } catch (e) {
    report.value = null
    props.notify(e.message || '读取运行记录失败')
  } finally {
    auditing.value = false
  }
}

// 深链消费：结果页"查看完整可信度审计"写入待审计记录后跳转过来。
// keep-alive 下 onActivated 在首次挂载与每次切回时都会触发。
function consumePending() {
  if (!pendingAuditRun.value && props.routeContext.run) pendingAuditRun.value = `run-${String(props.routeContext.run).replace(/^run-/, '')}`
  if (pendingAuditRun.value) {
    mode.value = '平台回测'
    const target = pendingAuditRun.value
    pendingAuditRun.value = null
    if (target !== selectedRun.value) {
      selectedRun.value = target
    } else if (!report.value) {
      loadAudit(target)
    }
  }
}

watch(selectedRun, loadAudit)
watch(() => props.routeContext.run, consumePending)
onMounted(async () => {
  consumePending()
  await loadRuns()
})
onActivated(consumePending)
</script>

<template>
  <div class="space-y-6">
    <!-- 标题 -->
    <div class="glass relative overflow-hidden rounded-2xl p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-indigo-500/20 blur-3xl" />
      <h1 class="text-xl font-bold text-white">可信度审计</h1>
      <p class="mt-1 text-sm text-slate-400">
        对已完成回测做六维可信度评级：数据完整性、未来函数防护、样本与选股偏差、成本真实性、容量约束、参数搜索偏差。评级回答的不是"赚不赚钱"，而是"这份结果有多少水分"。
      </p>
    </div>

    <!-- 审计对象切换 -->
    <div class="flex gap-2">
      <button
        v-for="m in ['平台回测', '外部材料']"
        :key="m"
        class="rounded-lg px-4 py-2 text-sm font-medium transition"
        :class="mode === m ? 'bg-indigo-500 text-white' : 'border border-white/10 bg-white/5 text-slate-400 hover:text-slate-200'"
        @click="mode = m"
      >{{ m }}</button>
    </div>

    <!-- 外部材料模式：委托给 StrategyForensicsView -->
    <StrategyForensicsView v-if="mode === '外部材料'" :user="user" :notify="notify" />

    <!-- 平台回测模式 -->
    <template v-else>
    <!-- 无记录 -->
    <SectionCard v-if="!loading && !runs.length" title="暂无可审计的回测记录">
      <p class="rounded-xl bg-white/5 px-3 py-2 text-sm text-slate-400">
        请先在「回测与验证」中运行一次回测，再回到本页查看可信度评级与证据链。
      </p>
    </SectionCard>

    <template v-else>
      <!-- 选择记录 -->
      <SectionCard title="选择回测记录" hint="仅显示引擎明细仍存在的成功记录">
        <div class="max-w-xl">
          <FormField type="select" label="回测记录" v-model="selectedRun" :options="runOptions" :disabled="loading || auditing" />
        </div>
      </SectionCard>

      <div v-if="loading" class="text-sm text-slate-400">加载中…</div>
      <div v-else-if="auditing" class="text-sm text-slate-400">审计中…</div>

      <template v-else-if="report">
        <!-- 评级仪表盘 -->
        <section class="grid gap-5 sm:grid-cols-2 xl:grid-cols-5">
          <MetricCard v-for="m in metrics" :key="m.label" :label="m.label" :value="m.value" :sub="m.sub" :tone="m.tone" />
        </section>
        <p
          class="rounded-xl border px-4 py-3 text-sm font-medium"
          :class="GRADE_BANNER[report.grade] || 'bg-white/5 text-slate-300 border-white/10'"
        >
          可信度评级 {{ report.grade }}——{{ report.headline }}
        </p>

        <!-- 六维审计 -->
        <SectionCard title="六维审计" hint="各维度的结论与首条要点">
          <DataTable :columns="dimensionCols" :rows="dimensionRows" empty="暂无审计维度">
            <template #cell-status="{ row }">
              <span class="inline-flex rounded-full border px-2.5 py-0.5 text-xs whitespace-nowrap" :class="STATUS_TONE[row.status] || 'text-slate-300 bg-white/5 border-white/10'">
                {{ STATUS_LABELS[row.status] || row.status }}
              </span>
            </template>
          </DataTable>
        </SectionCard>

        <!-- 参数搜索偏差（第六维证据） -->
        <SectionCard
          v-if="selection"
          title="参数搜索偏差"
          hint="本结果若来自参数网格搜索，校正后的显著性证据如下"
        >
          <div class="space-y-4">
            <p
              class="rounded-xl border px-4 py-3 text-sm font-medium"
              :class="SELECTION_BANNER[selection.status] || 'bg-white/5 text-slate-300 border-white/10'"
            >
              {{ selection.message }}
            </p>
            <section class="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard v-for="m in selectionMetrics" :key="m.label" :label="m.label" :value="m.value" :sub="m.sub" :tone="m.tone" />
            </section>
            <p class="text-xs leading-relaxed text-slate-500">{{ selection.scope_note }}</p>
            <details class="rounded-xl border border-white/10 bg-white/5 px-4 py-3">
              <summary class="cursor-pointer text-sm font-medium text-slate-300">计算依据与试验清单</summary>
              <div class="mt-3 space-y-4">
                <DataTable
                  :columns="[{ key: 'name', label: '计算依据' }, { key: 'value', label: '取值' }]"
                  :rows="selectionBasisRows"
                  empty="无计算记录"
                />
                <DataTable v-if="evidenceRows.length" :columns="evidenceCols" :rows="evidenceRows" empty="无试验记录" />
                <p class="text-xs leading-relaxed text-slate-500">
                  按同一收益日期、频率和无风险利率比较，使用日频 Sharpe、样本偏度与 Pearson 峰度计算；
                  DSR 仅衡量 Sharpe 的统计证据，不能替代样本外验证。
                </p>
              </div>
            </details>
          </div>
        </SectionCard>

        <!-- 维度明细 -->
        <SectionCard title="维度明细" hint="展开查看每个维度的全部审计发现">
          <div class="space-y-3">
            <div
              v-for="d in report.dimensions"
              :key="d.key"
              class="overflow-hidden rounded-xl border border-white/10 bg-white/5"
            >
              <button
                type="button"
                class="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition hover:bg-white/5"
                @click="toggleDim(d.key)"
              >
                <span class="flex items-center gap-2.5 text-sm font-medium text-slate-200">
                  <span
                    class="inline-flex rounded-full border px-2 py-0.5 text-xs"
                    :class="STATUS_TONE[d.status] || 'text-slate-300 bg-white/5 border-white/10'"
                  >{{ STATUS_LABELS[d.status] || d.status }}</span>
                  {{ d.title }}
                </span>
                <span class="text-xs text-slate-500">{{ expanded[d.key] ? '收起 ▲' : '展开 ▼' }}</span>
              </button>
              <div v-if="expanded[d.key]" class="space-y-2 border-t border-white/5 px-4 py-3">
                <p v-if="!d.findings?.length" class="text-xs text-slate-500">无审计发现。</p>
                <p
                  v-for="(f, i) in d.findings"
                  :key="i"
                  class="rounded-lg border px-3 py-2 text-xs leading-relaxed"
                  :class="SEVERITY_TONE[f.severity] || 'text-slate-400 border-white/10 bg-white/5'"
                >
                  [{{ SEVERITY_LABELS[f.severity] || f.severity }}] {{ f.message }}
                </p>
              </div>
            </div>
          </div>
        </SectionCard>

        <!-- 证据链 -->
        <SectionCard title="证据链" hint="引擎有效性审计的全部原始记录，评级结论均可追溯至此">
          <DataTable :columns="issueCols" :rows="issueRows" empty="无有效性问题记录">
            <template #cell-severity="{ row }">
              <span
                class="inline-flex rounded-full border px-2.5 py-0.5 text-xs whitespace-nowrap"
                :class="SEVERITY_TONE[row.severity] || 'text-slate-300 bg-white/5 border-white/10'"
              >{{ row.severity }}</span>
            </template>
          </DataTable>
        </SectionCard>

        <!-- 审计假设 -->
        <SectionCard title="审计假设" hint="本次评级采用的执行参数（来自运行配置快照）">
          <DataTable :columns="[{ key: 'name', label: '审计假设' }, { key: 'value', label: '取值' }]" :rows="assumptionRows" empty="未记录" />
        </SectionCard>
      </template>
    </template>
    </template>
  </div>
</template>
