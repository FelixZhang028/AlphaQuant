<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { getRunAudit, listAuditRuns } from '../../api.js'
import MetricCard from '../ui/MetricCard.vue'
import SectionCard from '../ui/SectionCard.vue'
import DataTable from '../ui/DataTable.vue'
import FormField from '../ui/FormField.vue'
import StrategyForensicsView from './StrategyForensicsView.vue'

const props = defineProps({
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
const STATUS_LABELS = { pass: '通过', warn: '警告', fail: '不通过' }
const STATUS_TONE = {
  pass: 'text-emerald-300 bg-emerald-400/10 border-emerald-400/30',
  warn: 'text-amber-300 bg-amber-400/10 border-amber-400/30',
  fail: 'text-rose-300 bg-rose-400/10 border-rose-400/30',
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
  const passed = (r.dimensions || []).filter((d) => d.status === 'pass').length
  const ratio =
    r.transaction_cost_ratio != null ? `${(Number(r.transaction_cost_ratio) * 100).toFixed(2)}%` : '—'
  return [
    { label: '可信度评级', value: r.grade, sub: '五维综合评级', tone: gradeTone.value },
    { label: '审计维度通过', value: `${passed}/5`, sub: '数据/未来函数/偏差/成本/容量' },
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

watch(selectedRun, loadAudit)
onMounted(loadRuns)
</script>

<template>
  <div class="space-y-6">
    <!-- 标题 -->
    <div class="glass relative overflow-hidden rounded-2xl p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-indigo-500/20 blur-3xl" />
      <h1 class="text-xl font-bold text-white">可信度审计</h1>
      <p class="mt-1 text-sm text-slate-400">
        对已完成回测做五维可信度评级：数据完整性、未来函数防护、样本与选股偏差、成本真实性、容量约束。评级回答的不是"赚不赚钱"，而是"这份结果有多少水分"。
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

        <!-- 五维审计 -->
        <SectionCard title="五维审计" hint="各维度的结论与首条要点">
          <DataTable :columns="dimensionCols" :rows="dimensionRows" empty="暂无审计维度">
            <template #cell-status="{ row }">
              <span class="inline-flex rounded-full border px-2.5 py-0.5 text-xs whitespace-nowrap" :class="STATUS_TONE[row.status] || 'text-slate-300 bg-white/5 border-white/10'">
                {{ STATUS_LABELS[row.status] || row.status }}
              </span>
            </template>
          </DataTable>
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
