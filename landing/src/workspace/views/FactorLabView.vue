<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import {
  compositeFactors,
  createCustomFactor,
  deleteCustomFactor,
  evaluateFactor,
  listFactors,
  researchFactors,
} from '../../api.js'
import MetricCard from '../ui/MetricCard.vue'
import SectionCard from '../ui/SectionCard.vue'
import DataTable from '../ui/DataTable.vue'
import LineChart from '../ui/LineChart.vue'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

const activeTab = ref('library')
const tabs = [
  { key: 'library', label: '因子库' },
  { key: 'evaluate', label: '因子评估' },
  { key: 'composite', label: '因子组合' },
  { key: 'research', label: '组合研究' },
  { key: 'custom', label: '自定义因子' },
]

// ---------- 工具 ----------
function fmtNum(v, digits = 2) {
  return typeof v === 'number' && isFinite(v) ? v.toFixed(digits) : '—'
}
function fmtPct(v, digits = 2) {
  return typeof v === 'number' && isFinite(v) ? (v * 100).toFixed(digits) + '%' : '—'
}
function signTone(v) {
  if (typeof v !== 'number' || !isFinite(v)) return { up: null, tone: '' }
  return v >= 0 ? { up: true, tone: 'text-emerald-300' } : { up: false, tone: 'text-rose-300' }
}
function directionLabel(d) {
  return d === 1 ? '正向' : d === -1 ? '反向' : '—'
}
function dateStr(d) {
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${dd}`
}
const _today = new Date()
const defaultStart = dateStr(new Date(_today.getFullYear() - 2, _today.getMonth(), _today.getDate()))
const defaultEnd = dateStr(_today)

// ---------- 因子库 ----------
const factors = ref([])
const factorsLoading = ref(false)

async function loadFactors() {
  factorsLoading.value = true
  try {
    const data = await listFactors()
    factors.value = data.factors || []
  } catch (e) {
    props.notify(e.message || '加载因子库失败')
  } finally {
    factorsLoading.value = false
  }
}

const factorOptions = computed(() =>
  factors.value.map((f) => ({ value: f.name, label: f.display_name || f.name }))
)

const factorCols = [
  { key: 'name', label: '因子名' },
  { key: 'display_name', label: '中文名' },
  { key: 'category', label: '类别' },
  { key: 'description', label: '说明' },
  { key: 'formula', label: '计算公式' },
  { key: 'direction', label: '方向' },
  { key: 'min_history', label: '最小历史', align: 'right' },
  { key: 'actions', label: '操作', align: 'right' },
]

// ---------- 因子详情便签（右侧滑出） ----------
const detailFactor = ref(null)
const detailOpen = ref(false)

// 内置因子的含义与作用说明（自定义因子走通用回退文案）
const FACTOR_NOTES = {
  alpha101_006: {
    meaning:
      '计算过去 10 个交易日开盘价与成交量相关系数并取负。量价同步（价涨量增）时相关系数高、因子值低；量价背离（放量滞涨或缩量上涨）时因子值高。',
    usage:
      '用于捕捉量价背离信号：成交量显著放大但价格未跟上时，该因子值变大，提示多空分歧加剧。源自 WorldQuant Alpha101 #6，原公式为美股设计，A股有效性建议先用「因子评估」独立验证。',
  },
  alpha101_012: {
    meaning:
      '成交量变化方向（今日较昨日增/减）与价格变化反方向的乘积：放量下跌或缩量上涨时为正值，放量上涨或缩量下跌时为负值。',
    usage:
      '短期量价背离/反转信号：正值代表量价不配合，常出现在趋势衰竭阶段。适合与短期反转、动量因子搭配，辅助捕捉短线拐点。',
  },
  alpha101_033: {
    meaning:
      '对「开盘价 / 收盘价 - 1」进行全市场截面排名。开盘价高于收盘价（当日收阴）时比例为正，排名越高代表当日开收盘结构越弱。',
    usage:
      '衡量单日开收盘结构的相对强度，属反转类因子：当日收阴越深的股票，后续存在均值回归（反弹）预期。源自 WorldQuant Alpha101 #33。',
  },
  alpha101_101: {
    meaning:
      '当日 K 线实体（收盘价 - 开盘价）占振幅（最高价 - 最低价）的比例。大实体代表单边趋势日，小实体（十字星）代表多空平衡。',
    usage:
      'K 线形态类因子：实体占比高说明当日单边力量强，可辅助判断趋势强度与延续性；与动量因子组合能过滤假突破。源自 WorldQuant Alpha101 #101。',
  },
  amount_change_20: {
    meaning: '近 5 日平均成交额相对近 20 日平均成交额的变化率：短期成交额明显高于长期均值时为正。',
    usage:
      '流动性/关注度因子：成交额短期放大通常意味着资金流入、市场关注度提升；过高时也可能预示过热。可作为组合的增强维度或风险提示。',
  },
  amplitude_20: {
    meaning: '近 20 个交易日的日均振幅（最高价 - 最低价）/ 昨收。数值越大，日内波动越剧烈。',
    usage:
      '波动与风险因子（反向使用）：高振幅股票短线机会多但风险大，低振幅股票走势更稳健。常用于构建低波动组合或过滤高风险标的。',
  },
  bias_10: {
    meaning: '当前价格相对 10 日均线的偏离百分比：价格高于均线越多，乖离率越大。',
    usage:
      '经典超买超卖指标（反向使用）：乖离率过大时，价格存在向均线回归（回调/反弹）的动力。适合作为反转策略的择时与选股信号。',
  },
  high_distance_20: {
    meaning: '当前收盘价距近 20 日最高价的比例距离：越接近 0，说明越贴近近期新高。',
    usage:
      '动量/突破因子：贴近新高的股票通常处于强势趋势中（强者恒强），适合动量策略；与成交量配合可确认突破有效性。',
  },
  momentum_20: {
    meaning: '近 20 个交易日的区间收益率（今收 / 20 日前收盘 - 1），最经典的动量指标。',
    usage:
      '趋势类核心因子：A股月度动量效应相对较弱且带有反转倾向，建议结合市场状态使用，或与反转、波动因子组合以平衡风格暴露。',
  },
  pv_corr_20: {
    meaning: '近 20 日价格与成交量的相关系数（反向使用）：量价同步上涨为正相关，量价背离为负相关。',
    usage:
      '量价配合度因子：健康的上涨通常伴随放量（正相关），缩量上涨持续性存疑。反向使用时偏向选择存在量价背离的标的。',
  },
  reversal_5: {
    meaning: '近 5 日收益率的相反数：短期跌幅越大，因子值越高。',
    usage:
      '短期反转因子：A股存在显著的短期反转效应，超跌股票在随后几天往往出现反弹。是短线策略与均值回归组合的常用成分。',
  },
  rsi_14: {
    meaning: '14 日相对强弱指标（Wilder 平滑），基于平均涨幅与平均跌幅之比，取值 0~100（反向使用）。',
    usage:
      '经典摆动指标（反向使用）：RSI 超买（>70）预示回调风险，超卖（<30）预示反弹机会。反向使用时超卖标的得分更高，与反转策略配合效果更好。',
  },
  volatility_20: {
    meaning: '近 20 日日收益率的标准差，衡量价格波动风险（反向使用）。',
    usage:
      '风险因子（反向使用）：低波动股票的长期风险调整后收益往往更优（低波动异象）。适合作为选股约束或低波组合的核心因子。',
  },
  volume_ratio_5: {
    meaning: '近 5 日平均成交量与近 20 日平均成交量之比：大于 1 说明近期成交活跃度提升。',
    usage:
      '成交量异动因子：量比放大代表资金关注或消息驱动，常作为突破确认信号；也需警惕高位放量出货，建议与价格趋势结合判断。',
  },
}

const detailNote = computed(() => {
  const f = detailFactor.value
  if (!f) return null
  return (
    FACTOR_NOTES[f.name] || {
      meaning: f.description || '自定义因子：由基础字段与算子组合计算而成。',
      usage: '在「自定义因子」页配置生成，可在因子评估、因子组合与组合研究中与其他因子一样参与合成与验证。',
    }
  )
})

function showFactorDetail(f) {
  detailFactor.value = f
  detailOpen.value = true
}

function closeDetail() {
  detailOpen.value = false
}

// 从便签一键跳去评估
function evaluateFromDetail() {
  if (!detailFactor.value) return
  evalForm.factor_name = detailFactor.value.name
  activeTab.value = 'evaluate'
  detailOpen.value = false
}

function onKeydown(e) {
  if (e.key === 'Escape') detailOpen.value = false
}

// ---------- 因子评估 ----------
const horizonOptions = [1, 5, 10, 20]
const groupOptions = [5, 10]

const evalForm = reactive({
  factor_name: '',
  horizon: 5,
  n_groups: 5,
  start_date: defaultStart,
  end_date: defaultEnd,
})
const evalLoading = ref(false)
const evalResult = ref(null)
const evalError = ref('')

async function runEvaluate() {
  if (!evalForm.factor_name) return props.notify('请选择因子')
  evalLoading.value = true
  evalError.value = ''
  evalResult.value = null
  try {
    evalResult.value = await evaluateFactor({
      factor_name: evalForm.factor_name,
      horizon: Number(evalForm.horizon),
      n_groups: Number(evalForm.n_groups),
      start_date: evalForm.start_date,
      end_date: evalForm.end_date,
    })
    props.notify('评估完成')
  } catch (e) {
    evalError.value = e.message || '评估失败'
    props.notify(e.message || '评估失败')
  } finally {
    evalLoading.value = false
  }
}

// ---------- 因子组合 ----------
const weightModes = [
  { value: 'equal', label: '等权' },
  { value: 'ic', label: 'IC加权' },
  { value: 'custom', label: '自定义' },
]

const compForm = reactive({
  factor_names: [],
  weight_mode: 'equal',
  winsorize: true,
  corr_threshold: 0.7,
  horizon: 5,
  n_groups: 5,
  start_date: defaultStart,
  end_date: defaultEnd,
})
const compWeights = reactive({})
const compLoading = ref(false)
const compResult = ref(null)
const compError = ref('')

function isSelected(name) {
  return compForm.factor_names.includes(name)
}
function toggleFactor(name) {
  const i = compForm.factor_names.indexOf(name)
  if (i >= 0) {
    compForm.factor_names.splice(i, 1)
  } else {
    compForm.factor_names.push(name)
    if (compWeights[name] == null) compWeights[name] = 1
  }
}

async function runComposite() {
  if (compForm.factor_names.length < 2) return props.notify('请至少选择两个因子')
  compLoading.value = true
  compError.value = ''
  compResult.value = null
  try {
    const payload = {
      factor_names: [...compForm.factor_names],
      weight_mode: compForm.weight_mode,
      winsorize: compForm.winsorize,
      zscore: false,
      fill_method: 'drop',
      corr_threshold: Number(compForm.corr_threshold),
      horizon: Number(compForm.horizon),
      n_groups: Number(compForm.n_groups),
      start_date: compForm.start_date,
      end_date: compForm.end_date,
    }
    if (compForm.weight_mode === 'custom') {
      payload.weights = {}
      compForm.factor_names.forEach((n) => {
        payload.weights[n] = Number(compWeights[n]) || 0
      })
    }
    compResult.value = await compositeFactors(payload)
    props.notify('合成因子评估完成')
  } catch (e) {
    compError.value = e.message || '合成失败'
    props.notify(e.message || '合成失败')
  } finally {
    compLoading.value = false
  }
}

// ---------- 组合研究（训练/测试集） ----------
// 迁移自 AlphaQuant 因子研究流程：训练期确定权重，测试期对比
// 各单因子 / 等权组合 / 我的组合的样本外表现。
const researchWeightModes = [
  { value: 'equal', label: '等权' },
  { value: 'ic', label: '训练期IC加权' },
  { value: 'manual', label: '自定义' },
]

const defaultTrainStart = dateStr(new Date(_today.getFullYear() - 2, _today.getMonth(), _today.getDate()))
const defaultTrainEnd = dateStr(new Date(_today.getFullYear() - 1, _today.getMonth(), _today.getDate()))
const defaultTestStart = dateStr(new Date(_today.getFullYear() - 1, _today.getMonth(), _today.getDate() + 1))
const defaultTestEnd = dateStr(_today)

const researchForm = reactive({
  factor_names: [],
  weight_mode: 'equal',
  clip: true,
  missing: 'drop',
  horizon: 5,
  n_groups: 5,
  train_start: defaultTrainStart,
  train_end: defaultTrainEnd,
  test_start: defaultTestStart,
  test_end: defaultTestEnd,
})
const researchWeights = reactive({})
const researchLoading = ref(false)
const researchResult = ref(null)
const researchError = ref('')

function toggleResearchFactor(name) {
  const i = researchForm.factor_names.indexOf(name)
  if (i >= 0) {
    researchForm.factor_names.splice(i, 1)
  } else {
    researchForm.factor_names.push(name)
    if (researchWeights[name] == null) researchWeights[name] = 1
  }
}

const comparisonCols = [
  { key: '方案', label: '方案' },
  { key: 'Rank IC', label: 'Rank IC', align: 'right' },
  { key: 'Rank IC IR', label: 'Rank IC IR', align: 'right' },
  { key: 'IC', label: 'IC', align: 'right' },
  { key: '同日多空收益差', label: '多空收益差', align: 'right' },
  { key: '成员更替率', label: '成员更替率', align: 'right' },
  { key: '有效 IC 天数', label: '有效IC天数', align: 'right' },
]

const researchCorrRows = computed(() => {
  const corr = researchResult.value?.correlation_matrix || {}
  const names = researchForm.factor_names
  return names.map((n) => ({ name: n, ...corr[n] }))
})
const researchCorrCols = computed(() => [
  { key: 'name', label: '因子' },
  ...researchForm.factor_names.map((n) => ({ key: n, label: n, align: 'right' })),
])

async function runResearch() {
  if (researchForm.factor_names.length < 2) return props.notify('请至少选择两个因子')
  researchLoading.value = true
  researchError.value = ''
  researchResult.value = null
  try {
    const payload = {
      factor_names: [...researchForm.factor_names],
      weight_mode: researchForm.weight_mode,
      clip: researchForm.clip,
      missing: researchForm.missing,
      horizon: Number(researchForm.horizon),
      n_groups: Number(researchForm.n_groups),
      train_start: researchForm.train_start,
      train_end: researchForm.train_end,
      test_start: researchForm.test_start,
      test_end: researchForm.test_end,
    }
    if (researchForm.weight_mode === 'manual') {
      payload.weights = {}
      researchForm.factor_names.forEach((n) => {
        payload.weights[n] = Number(researchWeights[n]) || 0
      })
    }
    researchResult.value = await researchFactors(payload)
    props.notify('组合研究完成')
  } catch (e) {
    researchError.value = e.message || '研究失败'
    props.notify(e.message || '研究失败')
  } finally {
    researchLoading.value = false
  }
}

// ---------- 自定义因子 ----------
const fieldOptions = [
  { value: 'adjusted_close', label: '后复权收盘价' },
  { value: 'raw_open', label: '开盘价' },
  { value: 'raw_high', label: '最高价' },
  { value: 'raw_low', label: '最低价' },
  { value: 'pre_close', label: '昨收盘价' },
  { value: 'volume', label: '成交量' },
  { value: 'amount', label: '成交额' },
]
const operatorOptions = [
  { value: 'momentum', label: '动量' },
  { value: 'bias', label: '乖离率' },
  { value: 'sma', label: '简单均线' },
  { value: 'rolling_std', label: '滚动标准差' },
  { value: 'volatility', label: '波动率' },
  { value: 'ma_ratio', label: '均线比' },
  { value: 'pv_corr', label: '量价相关' },
]
const directionOptions = [
  { value: 1, label: '正向' },
  { value: -1, label: '反向' },
]

const customForm = reactive({
  name: '',
  display_name: '',
  field: 'adjusted_close',
  operator: 'momentum',
  window: 20,
  window2: null,
  direction: 1,
})
const customLoading = ref(false)

const customFactors = computed(() => factors.value.filter((f) => f.category === '自定义'))
const customCols = [
  { key: 'name', label: '标识' },
  { key: 'display_name', label: '显示名' },
  { key: 'formula', label: '公式' },
  { key: 'min_history', label: '最小历史', align: 'right' },
  { key: 'direction', label: '方向' },
  { key: 'actions', label: '操作', align: 'right' },
]

async function onSubmitCustom() {
  const name = customForm.name.trim()
  if (!name) return props.notify('请输入因子标识')
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) {
    return props.notify('标识需以字母或下划线开头，仅含字母/数字/下划线')
  }
  if (!customForm.window || Number(customForm.window) < 1) return props.notify('请输入有效窗口')
  if (customForm.operator === 'ma_ratio' && (!customForm.window2 || Number(customForm.window2) <= Number(customForm.window))) {
    return props.notify('均线比的第二窗口需大于第一窗口')
  }
  customLoading.value = true
  try {
    const payload = {
      name,
      display_name: customForm.display_name.trim(),
      description: '',
      field: customForm.field,
      operator: customForm.operator,
      window: Number(customForm.window),
      direction: Number(customForm.direction),
    }
    if (customForm.operator === 'ma_ratio') payload.window2 = Number(customForm.window2)
    await createCustomFactor(payload)
    props.notify('自定义因子已添加')
    customForm.name = ''
    customForm.display_name = ''
    customForm.window2 = null
    await loadFactors()
  } catch (e) {
    props.notify(e.message || '添加失败')
  } finally {
    customLoading.value = false
  }
}

async function onDeleteCustom(f) {
  if (!confirm(`确定删除自定义因子「${f.display_name || f.name}」？`)) return
  try {
    await deleteCustomFactor(f.name)
    props.notify('已删除')
    await loadFactors()
  } catch (e) {
    props.notify(e.message || '删除失败')
  }
}

// ---------- 评估报告（评估与组合复用） ----------
function buildReportView(report) {
  if (!report) return null
  const metrics = [
    { label: 'IC 均值', value: fmtNum(report.ic_mean, 3), sub: 'Pearson IC', ...signTone(report.ic_mean) },
    { label: 'Rank IC 均值', value: fmtNum(report.rank_ic_mean, 3), sub: 'Spearman IC', ...signTone(report.rank_ic_mean) },
    { label: 'Rank IC IR', value: fmtNum(report.rank_ic_ir, 3), sub: 'IC 稳定性', ...signTone(report.rank_ic_ir) },
    { label: '多空收益', value: fmtPct(report.long_short_mean, 2), sub: `持有 ${report.horizon} 日`, ...signTone(report.long_short_mean) },
  ]
  const stability = [
    { label: '前半段 IC', value: fmtNum(report.first_half_ic, 3), sub: '样本前半段', ...signTone(report.first_half_ic) },
    { label: '后半段 IC', value: fmtNum(report.second_half_ic, 3), sub: '样本后半段', ...signTone(report.second_half_ic) },
    { label: '平均换手率', value: fmtPct(report.turnover_mean, 2), sub: '组合调仓换手', up: null, tone: '' },
  ]
  const daily = report.daily_ic || []
  const series = [
    { label: 'IC', color: '#818cf8', points: daily.map((d) => d.ic) },
    { label: 'Rank IC', color: '#a78bfa', points: daily.map((d) => d.rank_ic) },
  ]
  const n = report.n_groups || 5
  const groupCols = Array.from({ length: n }, (_, i) => ({
    key: `G${i + 1}`,
    label: `G${i + 1}`,
    align: 'right',
  }))
  const g = report.group_mean_returns || {}
  const groupRows = [Object.fromEntries(Object.entries(g).map(([k, v]) => [k, fmtPct(v, 2)]))]
  return { metrics, stability, series, groupCols, groupRows, notes: report.notes }
}

const evalView = computed(() => buildReportView(evalResult.value))
const compView = computed(() => buildReportView(compResult.value?.report))

// 相关性矩阵
const corrNames = computed(() => (compResult.value ? Object.keys(compResult.value.correlation_matrix || {}) : []))
const corrCols = computed(() => [
  { key: '_name', label: '因子' },
  ...corrNames.value.map((n) => ({ key: n, label: n, align: 'right' })),
])
const corrRows = computed(() => {
  const m = compResult.value?.correlation_matrix || {}
  return corrNames.value.map((n) => {
    const row = { _name: n }
    corrNames.value.forEach((k) => {
      row[k] = m[n] && m[n][k] != null ? Number(m[n][k]).toFixed(2) : '—'
    })
    return row
  })
})
const weightCaption = computed(() => {
  const spec = compResult.value?.composite_spec || []
  if (!spec.length) return ''
  return spec.map((s) => `${s.name} ${fmtPct(Number(s.weight), 2)}`).join(' · ')
})

onMounted(() => {
  loadFactors()
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="space-y-6">
    <!-- 标题 -->
    <div class="glass glass-sheen relative overflow-hidden rounded-2xl p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-indigo-500/20 blur-3xl" />
      <p class="text-2xl font-bold text-white">因子实验室</p>
      <p class="mt-2 max-w-xl text-sm text-slate-400">IC/Rank IC/分层收益评估，多因子合成选股；点击「详情」查看因子说明</p>
    </div>

    <!-- Tab -->
    <div class="flex flex-wrap items-center gap-2">
      <div class="flex rounded-full border border-white/10 bg-white/5 p-0.5 text-xs">
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
    </div>

    <!-- ============ 因子库 ============ -->
    <template v-if="activeTab === 'library'">
      <SectionCard title="因子库" hint="内置因子与自定义因子，方向 1 表示正向、-1 表示反向">
        <div v-if="factorsLoading" class="py-8 text-sm text-slate-400">加载中…</div>
        <DataTable v-else :columns="factorCols" :rows="factors" empty="暂无因子">
          <template #cell-direction="{ value }">
            <span :class="value === 1 ? 'text-emerald-300' : value === -1 ? 'text-rose-300' : 'text-slate-400'">
              {{ directionLabel(value) }}
            </span>
          </template>
          <template #cell-actions="{ row }">
            <button
              @click="showFactorDetail(row)"
              class="rounded-lg border border-indigo-400/20 bg-indigo-500/10 px-2.5 py-1 text-xs text-indigo-300 transition hover:bg-indigo-400/20"
            >
              详情
            </button>
          </template>
        </DataTable>
      </SectionCard>
    </template>

    <!-- ============ 因子评估 ============ -->
    <template v-else-if="activeTab === 'evaluate'">
      <SectionCard title="因子评估" hint="选择因子与参数，计算 IC / Rank IC / 分层收益">
        <div class="grid gap-4 md:grid-cols-5">
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">因子</span>
            <select v-model="evalForm.factor_name" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40">
              <option value="" disabled>请选择因子</option>
              <option v-for="o in factorOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </label>
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">持有期</span>
            <select v-model="evalForm.horizon" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40">
              <option v-for="h in horizonOptions" :key="h" :value="h">{{ h }} 日</option>
            </select>
          </label>
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">分组数</span>
            <select v-model="evalForm.n_groups" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40">
              <option v-for="g in groupOptions" :key="g" :value="g">{{ g }} 组</option>
            </select>
          </label>
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">开始日期</span>
            <input v-model="evalForm.start_date" type="date" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
          </label>
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">结束日期</span>
            <input v-model="evalForm.end_date" type="date" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
          </label>
        </div>
        <div class="mt-5 flex items-center gap-3">
          <button
            @click="runEvaluate"
            :disabled="evalLoading"
            class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
          >
            {{ evalLoading ? '评估中…' : '开始评估' }}
          </button>
          <button
            v-if="evalForm.factor_name"
            @click="showFactorDetail(factors.find((f) => f.name === evalForm.factor_name))"
            class="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-300 transition hover:border-indigo-400/40 hover:text-white"
          >
            因子详情
          </button>
          <p v-if="evalError" class="text-sm text-rose-300">{{ evalError }}</p>
        </div>
      </SectionCard>

      <template v-if="evalView">
        <section class="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard v-for="m in evalView.metrics" :key="m.label" :label="m.label" :value="m.value" :sub="m.sub" :up="m.up" :tone="m.tone" />
        </section>

        <SectionCard title="稳定性" hint="样本分段 IC 与调仓换手">
          <div class="grid gap-5 sm:grid-cols-3">
            <MetricCard v-for="s in evalView.stability" :key="s.label" :label="s.label" :value="s.value" :sub="s.sub" :up="s.up" :tone="s.tone" />
          </div>
        </SectionCard>

        <SectionCard title="Rank IC 时序" hint="日度 IC / Rank IC 曲线">
          <LineChart :series="evalView.series" :height="180" />
        </SectionCard>

        <SectionCard title="分层收益" hint="按因子值排序分为 N 组，各组平均收益">
          <DataTable :columns="evalView.groupCols" :rows="evalView.groupRows" empty="暂无数据" />
        </SectionCard>
      </template>
    </template>

    <!-- ============ 因子组合 ============ -->
    <template v-else-if="activeTab === 'composite'">
      <SectionCard title="合成配置" hint="选择至少两个因子，计算相关性并合成评估">
        <div class="mb-1 flex items-center justify-between">
          <span class="text-xs text-slate-400">因子（已选 {{ compForm.factor_names.length }} 个，至少 2 个）</span>
        </div>
        <div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          <label
            v-for="f in factors"
            :key="f.name"
            class="flex cursor-pointer items-center gap-2.5 rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-slate-300 transition hover:bg-white/10"
            :class="isSelected(f.name) ? 'border-indigo-400/40' : ''"
          >
            <input type="checkbox" :checked="isSelected(f.name)" @change="toggleFactor(f.name)" class="h-4 w-4 rounded border-white/20 bg-white/5 accent-indigo-500" />
            <span class="flex-1 truncate">{{ f.display_name || f.name }}</span>
            <span class="text-xs text-slate-500">{{ f.name }}</span>
            <button
              type="button"
              title="查看因子详情"
              class="shrink-0 rounded-md p-1 text-slate-500 transition hover:bg-white/10 hover:text-indigo-300"
              @click.stop.prevent="showFactorDetail(f)"
            >
              <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" /></svg>
            </button>
          </label>
        </div>

        <div class="mt-5 grid gap-5 lg:grid-cols-2">
          <div>
            <span class="mb-1.5 block text-xs text-slate-400">权重方式</span>
            <div class="flex w-fit rounded-full border border-white/10 bg-white/5 p-0.5 text-xs">
              <button
                v-for="m in weightModes"
                :key="m.value"
                @click="compForm.weight_mode = m.value"
                class="rounded-full px-3 py-1 transition"
                :class="compForm.weight_mode === m.value ? 'bg-gradient-to-r from-indigo-500 to-violet-500 text-white' : 'text-slate-400 hover:text-slate-200'"
              >
                {{ m.label }}
              </button>
            </div>
            <div v-if="compForm.weight_mode === 'custom'" class="mt-3 grid gap-3 sm:grid-cols-2">
              <label v-for="n in compForm.factor_names" :key="n" class="block">
                <span class="mb-1 block text-xs text-slate-400">权重 · {{ n }}</span>
                <input v-model.number="compWeights[n]" type="number" min="0" step="0.05" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
              </label>
            </div>
          </div>
          <div class="space-y-4">
            <label class="flex items-center gap-2.5">
              <input type="checkbox" v-model="compForm.winsorize" class="h-4 w-4 rounded border-white/20 bg-white/5 accent-indigo-500" />
              <span class="text-sm text-slate-300">去极值（Winsorize）</span>
            </label>
            <label class="block">
              <span class="mb-1 block text-xs text-slate-400">相关性阈值 {{ Number(compForm.corr_threshold).toFixed(2) }}</span>
              <input v-model.number="compForm.corr_threshold" type="range" min="0.5" max="0.95" step="0.05" class="w-full accent-indigo-500" />
            </label>
          </div>
        </div>

        <div class="mt-5 grid gap-4 md:grid-cols-4">
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">持有期</span>
            <select v-model="compForm.horizon" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40">
              <option v-for="h in horizonOptions" :key="h" :value="h">{{ h }} 日</option>
            </select>
          </label>
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">分组数</span>
            <select v-model="compForm.n_groups" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40">
              <option v-for="g in groupOptions" :key="g" :value="g">{{ g }} 组</option>
            </select>
          </label>
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">开始日期</span>
            <input v-model="compForm.start_date" type="date" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
          </label>
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">结束日期</span>
            <input v-model="compForm.end_date" type="date" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
          </label>
        </div>

        <div class="mt-5 flex items-center gap-3">
          <button
            @click="runComposite"
            :disabled="compLoading"
            class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
          >
            {{ compLoading ? '计算中…' : '计算并评估合成因子' }}
          </button>
          <p v-if="compError" class="text-sm text-rose-300">{{ compError }}</p>
        </div>
      </SectionCard>

      <template v-if="compResult">
        <SectionCard title="因子相关性矩阵" hint="两两因子的相关系数">
          <DataTable :columns="corrCols" :rows="corrRows" empty="暂无数据" />
        </SectionCard>

        <div class="rounded-xl border border-white/10 bg-white/5 p-4">
          <p class="text-xs text-slate-400">合成权重</p>
          <p class="mt-1 text-sm text-white">{{ weightCaption || '—' }}</p>
          <p v-if="compResult.dropped_factors && compResult.dropped_factors.length" class="mt-1 text-xs text-amber-300">
            已剔除高相关因子：{{ compResult.dropped_factors.join('、') }}
          </p>
        </div>

        <template v-if="compView">
          <section class="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard v-for="m in compView.metrics" :key="m.label" :label="m.label" :value="m.value" :sub="m.sub" :up="m.up" :tone="m.tone" />
          </section>

          <SectionCard title="稳定性" hint="合成因子样本分段 IC 与调仓换手">
            <div class="grid gap-5 sm:grid-cols-3">
              <MetricCard v-for="s in compView.stability" :key="s.label" :label="s.label" :value="s.value" :sub="s.sub" :up="s.up" :tone="s.tone" />
            </div>
          </SectionCard>

          <SectionCard title="合成因子 Rank IC 时序" hint="日度 IC / Rank IC 曲线">
            <LineChart :series="compView.series" :height="180" />
          </SectionCard>

          <SectionCard title="合成因子分层收益" hint="按合成因子值排序分为 N 组，各组平均收益">
            <DataTable :columns="compView.groupCols" :rows="compView.groupRows" empty="暂无数据" />
          </SectionCard>
        </template>
      </template>
    </template>

    <!-- ============ 组合研究（训练/测试集） ============ -->
    <template v-else-if="activeTab === 'research'">
      <SectionCard title="研究配置" hint="先用训练期确定规则，再用独立测试期比较选股能力；实际收益与回撤请到回测页验证">
        <p class="text-xs text-slate-400">因子（已选 {{ researchForm.factor_names.length }} 个，至少 2 个）</p>
        <div class="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          <label
            v-for="f in factors"
            :key="f.name"
            class="flex cursor-pointer items-center gap-2.5 rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-slate-300 transition hover:bg-white/10"
            :class="researchForm.factor_names.includes(f.name) ? 'border-indigo-400/40' : ''"
          >
            <input type="checkbox" :checked="researchForm.factor_names.includes(f.name)" @change="toggleResearchFactor(f.name)" class="h-4 w-4 rounded border-white/20 bg-white/5 accent-indigo-500" />
            <span class="flex-1 truncate">{{ f.display_name || f.name }}</span>
            <span class="text-xs text-slate-500">{{ f.name }}</span>
            <button
              type="button"
              title="查看因子详情"
              class="shrink-0 rounded-md p-1 text-slate-500 transition hover:bg-white/10 hover:text-indigo-300"
              @click.stop.prevent="showFactorDetail(f)"
            >
              <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" /></svg>
            </button>
          </label>
        </div>

        <div class="mt-5 grid gap-5 lg:grid-cols-2">
          <div>
            <span class="mb-1.5 block text-xs text-slate-400">权重方式（只用训练期数据确定）</span>
            <div class="flex w-fit rounded-full border border-white/10 bg-white/5 p-0.5 text-xs">
              <button
                v-for="m in researchWeightModes"
                :key="m.value"
                @click="researchForm.weight_mode = m.value"
                class="rounded-full px-3 py-1 transition"
                :class="researchForm.weight_mode === m.value ? 'bg-gradient-to-r from-indigo-500 to-violet-500 text-white' : 'text-slate-400 hover:text-slate-200'"
              >
                {{ m.label }}
              </button>
            </div>
            <p class="mt-2 text-xs text-slate-500">训练期 IC 加权：正 IC 参与分配，负 IC 或无效值权重为零。</p>
            <div v-if="researchForm.weight_mode === 'manual'" class="mt-3 grid gap-3 sm:grid-cols-2">
              <label v-for="n in researchForm.factor_names" :key="n" class="block">
                <span class="mb-1 block text-xs text-slate-400">权重 · {{ n }}</span>
                <input v-model.number="researchWeights[n]" type="number" min="0" step="0.05" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
              </label>
            </div>
          </div>
          <div class="space-y-4">
            <label class="flex items-center gap-2.5">
              <input type="checkbox" v-model="researchForm.clip" class="h-4 w-4 rounded border-white/20 bg-white/5 accent-indigo-500" />
              <span class="text-sm text-slate-300">去极值（Winsorize）</span>
            </label>
            <label class="block">
              <span class="mb-1 block text-xs text-slate-400">缺失样本处理</span>
              <select v-model="researchForm.missing" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40">
                <option value="drop">剔除缺失（严格）</option>
                <option value="median">中位数填充</option>
              </select>
            </label>
          </div>
        </div>

        <div class="mt-5 grid gap-4 md:grid-cols-4">
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">训练开始</span>
            <input v-model="researchForm.train_start" type="date" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
          </label>
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">训练结束</span>
            <input v-model="researchForm.train_end" type="date" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
          </label>
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">测试开始</span>
            <input v-model="researchForm.test_start" type="date" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
          </label>
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">测试结束</span>
            <input v-model="researchForm.test_end" type="date" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
          </label>
        </div>

        <div class="mt-5 grid gap-4 md:grid-cols-2">
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">持有期</span>
            <select v-model="researchForm.horizon" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40">
              <option v-for="h in horizonOptions" :key="h" :value="h">{{ h }} 日</option>
            </select>
          </label>
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">分组数</span>
            <select v-model="researchForm.n_groups" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40">
              <option v-for="g in groupOptions" :key="g" :value="g">{{ g }} 组</option>
            </select>
          </label>
        </div>

        <div class="mt-5 flex items-center gap-3">
          <button
            @click="runResearch"
            :disabled="researchLoading"
            class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
          >
            {{ researchLoading ? '研究中…' : '运行组合研究' }}
          </button>
          <p v-if="researchError" class="text-sm text-rose-300">{{ researchError }}</p>
        </div>
      </SectionCard>

      <template v-if="researchResult">
        <div class="rounded-xl border border-white/10 bg-white/5 p-4">
          <p class="text-xs text-slate-400">研究区间</p>
          <p class="mt-1 text-sm text-white">
            训练期 {{ researchResult.train_start }} ~ {{ researchResult.train_end }}（确定权重）；
            测试期 {{ researchResult.test_start }} ~ {{ researchResult.test_end }}（样本外比较）
          </p>
          <p class="mt-1 text-xs text-slate-500">
            反复查看测试结果并调参会让测试集失去独立性，正式使用前还应保留新的未见数据。
          </p>
        </div>

        <SectionCard title="测试期结果对比" hint="各单因子 / 等权组合 / 我的组合在独立测试期的表现">
          <DataTable :columns="comparisonCols" :rows="researchResult.comparison" empty="暂无数据" />
        </SectionCard>

        <SectionCard title="训练期因子相关性" hint="训练期两两因子相关系数">
          <DataTable :columns="researchCorrCols" :rows="researchCorrRows" empty="暂无数据" />
        </SectionCard>

        <div class="rounded-xl border border-white/10 bg-white/5 p-4">
          <p class="text-xs text-slate-400">我的组合权重（训练期确定）</p>
          <p class="mt-1 text-sm text-white">
            <template v-if="researchResult.weights && Object.keys(researchResult.weights).length">
              <span v-for="(w, n) in researchResult.weights" :key="n" class="mr-4">{{ n }}：{{ (w * 100).toFixed(1) }}%</span>
            </template>
            <span v-else>—</span>
          </p>
        </div>
      </template>
    </template>

    <!-- ============ 自定义因子 ============ -->
    <template v-else>
      <SectionCard title="定义自定义因子" hint="基于字段与算子构造自定义因子，添加后可在因子库与评估中使用">
        <div class="grid gap-4 md:grid-cols-2">
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">标识</span>
            <input v-model="customForm.name" placeholder="如 my_factor_1" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
          </label>
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">显示名</span>
            <input v-model="customForm.display_name" placeholder="如 自定义动量因子" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
          </label>
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">字段</span>
            <select v-model="customForm.field" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40">
              <option v-for="o in fieldOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </label>
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">算子</span>
            <select v-model="customForm.operator" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40">
              <option v-for="o in operatorOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </label>
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">窗口</span>
            <input v-model.number="customForm.window" type="number" min="1" step="1" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
          </label>
          <label v-if="customForm.operator === 'ma_ratio'" class="block">
            <span class="mb-1 block text-xs text-slate-400">第二窗口（需大于窗口）</span>
            <input v-model.number="customForm.window2" type="number" min="1" step="1" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
          </label>
          <div class="md:col-span-2">
            <span class="mb-1.5 block text-xs text-slate-400">方向</span>
            <div class="flex items-center gap-5">
              <label v-for="d in directionOptions" :key="d.value" class="flex items-center gap-1.5 text-sm text-slate-300">
                <input type="radio" :value="d.value" v-model="customForm.direction" class="h-4 w-4 accent-indigo-500" />
                {{ d.label }}
              </label>
            </div>
          </div>
        </div>
        <div class="mt-5">
          <button
            @click="onSubmitCustom"
            :disabled="customLoading"
            class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
          >
            {{ customLoading ? '添加中…' : '添加因子' }}
          </button>
        </div>
      </SectionCard>

      <SectionCard title="已定义自定义因子" hint="从因子库中筛选 category === '自定义' 的因子">
        <DataTable :columns="customCols" :rows="customFactors" empty="暂无自定义因子">
          <template #cell-direction="{ value }">
            <span :class="value === 1 ? 'text-emerald-300' : 'text-rose-300'">{{ directionLabel(value) }}</span>
          </template>
          <template #cell-actions="{ row }">
            <div class="flex justify-end gap-2">
              <button @click="showFactorDetail(row)" class="rounded-lg border border-indigo-400/20 bg-indigo-500/10 px-2.5 py-1 text-xs text-indigo-300 transition hover:bg-indigo-400/20">详情</button>
              <button @click="onDeleteCustom(row)" class="rounded-lg border border-rose-400/20 px-2.5 py-1 text-xs text-rose-300 transition hover:bg-rose-400/10">删除</button>
            </div>
          </template>
        </DataTable>
      </SectionCard>
    </template>

    <!-- ============ 因子详情便签（右侧滑出） ============ -->
    <transition
      enter-active-class="transition duration-300 ease-out-expo"
      enter-from-class="translate-x-full opacity-40"
      enter-to-class="translate-x-0 opacity-100"
      leave-active-class="transition duration-300 ease-in"
      leave-from-class="translate-x-0 opacity-100"
      leave-to-class="translate-x-full opacity-40"
    >
      <aside
        v-if="detailOpen && detailFactor"
        class="fixed inset-y-0 right-0 z-[70] flex w-full max-w-[400px] flex-col border-l border-white/10 bg-ink/95 shadow-2xl shadow-black/40 backdrop-blur-xl"
      >
        <!-- 头部 -->
        <div class="flex items-start justify-between gap-3 border-b border-white/10 px-5 py-4">
          <div class="min-w-0">
            <p class="truncate text-base font-semibold text-white">{{ detailFactor.display_name }}</p>
            <p class="mt-0.5 font-mono text-xs text-indigo-300">{{ detailFactor.name }}</p>
          </div>
          <button
            @click="closeDetail"
            class="shrink-0 rounded-lg p-1.5 text-slate-400 transition hover:bg-white/10 hover:text-white"
            title="关闭"
          >
            <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <!-- 主体 -->
        <div class="flex-1 space-y-5 overflow-y-auto px-5 py-5">
          <!-- 标签 -->
          <div class="flex flex-wrap gap-2">
            <span class="rounded-full border border-indigo-400/30 bg-indigo-500/10 px-2.5 py-0.5 text-xs text-indigo-300">{{ detailFactor.category }}</span>
            <span class="rounded-full border border-white/10 bg-white/5 px-2.5 py-0.5 text-xs text-slate-400">{{ detailFactor.logical_category }}</span>
            <span class="rounded-full border border-white/10 bg-white/5 px-2.5 py-0.5 text-xs text-slate-400">{{ detailFactor.source }}</span>
            <span
              class="rounded-full border px-2.5 py-0.5 text-xs"
              :class="detailFactor.direction === 1 ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300' : 'border-rose-400/30 bg-rose-400/10 text-rose-300'"
            >
              {{ directionLabel(detailFactor.direction) }}
            </span>
          </div>

          <!-- 是什么 -->
          <section>
            <h3 class="text-xs font-semibold uppercase tracking-wider text-slate-500">是什么</h3>
            <p class="mt-2 text-sm leading-relaxed text-slate-300">{{ detailNote?.meaning }}</p>
          </section>

          <!-- 计算公式 -->
          <section>
            <h3 class="text-xs font-semibold uppercase tracking-wider text-slate-500">计算公式</h3>
            <code class="mt-2 block overflow-x-auto rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 font-mono text-xs text-emerald-300">{{ detailFactor.formula || '—' }}</code>
          </section>

          <!-- 有什么作用 -->
          <section>
            <h3 class="text-xs font-semibold uppercase tracking-wider text-slate-500">有什么作用</h3>
            <p class="mt-2 text-sm leading-relaxed text-slate-300">{{ detailNote?.usage }}</p>
          </section>

          <!-- 依赖字段 -->
          <section v-if="detailFactor.required_fields?.length">
            <h3 class="text-xs font-semibold uppercase tracking-wider text-slate-500">依赖数据字段</h3>
            <ul class="mt-2 space-y-2.5">
              <li v-for="rf in detailFactor.required_fields" :key="rf.field">
                <p class="text-sm text-slate-200">
                  {{ rf.label }}
                  <span class="ml-1 font-mono text-xs text-slate-500">{{ rf.field }}</span>
                </p>
                <p class="mt-0.5 text-xs leading-relaxed text-slate-500">{{ rf.note }}</p>
              </li>
            </ul>
          </section>

          <!-- 元信息 -->
          <section class="space-y-1.5 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-xs text-slate-500">
            <p>最小历史窗口：{{ detailFactor.min_history }} 个交易日</p>
            <p>
              版本：{{ detailFactor.version }}
              <template v-if="detailFactor.source_url">
                ·
                <a :href="detailFactor.source_url" target="_blank" rel="noopener" class="text-indigo-300 transition hover:underline">因子来源</a>
              </template>
            </p>
          </section>
        </div>

        <!-- 底部操作 -->
        <div class="border-t border-white/10 px-5 py-4">
          <button
            @click="evaluateFromDetail"
            class="w-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5"
          >
            评估该因子
          </button>
        </div>
      </aside>
    </transition>

    <!-- 遮罩 -->
    <transition
      enter-active-class="transition-opacity duration-300"
      enter-from-class="opacity-0"
      leave-active-class="transition-opacity duration-300"
      leave-to-class="opacity-0"
    >
      <div v-if="detailOpen" class="fixed inset-0 z-[60] bg-black/40 backdrop-blur-sm" @click="closeDetail" />
    </transition>
  </div>
</template>
