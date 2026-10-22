<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { createPackage, nlGenerate, nlStatus, preflightPackage, studioOptions } from '../../api.js'
import { remainingText } from '../aiPresentation.js'
import { openResearch } from '../researchNavigation.js'
import { blankForm, blankRule, chooseIndicator, formFromDefinition, packagePayload } from '../ruleForm.js'
import FormField from '../ui/FormField.vue'
import SectionCard from '../ui/SectionCard.vue'
import StrategySaved from '../ui/StrategySaved.vue'

const props = defineProps({
  routeContext: { type: Object, default: () => ({}) },
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

const MAX_RULES = 10
const STARTS = [
  { key: 'template', label: '从模板开始', hint: '选一个现成的思路，规则会填进下面的表单' },
  { key: 'describe', label: '用一句话描述', hint: '写下想法，由大模型转成规则' },
  { key: 'blank', label: '自己填', hint: '从一条空白条件开始' },
]
const freqOptions = [{ value: 'daily', label: '每日' }, { value: 'weekly', label: '每周' }, { value: 'monthly', label: '每月' }]
const dirOptions = [{ value: 'descending', label: '从高到低' }, { value: 'ascending', label: '从低到高' }]
const styleOptions = [{ value: 'conservative', label: '保守' }, { value: 'balanced', label: '均衡' }, { value: 'aggressive', label: '激进' }]
const logicOptions = [{ value: 'all', label: '全部满足' }, { value: 'any', label: '满足任意一条' }]
const compareOptions = [{ value: 'value', label: '一个数值' }, { value: 'indicator', label: '另一个指标' }]

const options = ref(null)
const loadError = ref('')
const form = ref(null)
// 表单是从哪里开始的：{ kind: 'template', template_id, style } | { kind: 'describe' } | null
const origin = ref(null)
const savedAsset = ref(null)
const saving = ref(false)

const select = (mapping) => Object.entries(mapping || {}).map(([value, label]) => ({ value, label }))
const indicatorOptions = computed(() => select(options.value?.indicators))
const operatorOptions = computed(() => select(options.value?.operators))
const windowLimits = (name) => options.value.indicator_windows[name]

// ---------- 三种开始方式 ----------
// 旧链接里的 mode=builder 对应现在的“自己填”。
const startFor = (mode) => (mode === 'builder' ? 'blank' : STARTS.some((item) => item.key === mode) ? mode : 'template')
const start = ref(startFor(props.routeContext.mode))
const tpl = reactive({ template_id: '', style: 'balanced' })
const templateOptions = computed(() => (options.value?.templates || []).map((t) => ({ value: t.template_id, label: t.name })))
const currentTemplate = computed(() => (options.value?.templates || []).find((t) => t.template_id === tpl.template_id))

function applyTemplate() {
  const template = currentTemplate.value
  const preset = template?.presets?.[tpl.style]
  if (!preset) return
  form.value = { ...formFromDefinition(preset.definition, preset, options.value), name: template.name }
  origin.value = { kind: 'template', template_id: template.template_id, style: tpl.style }
}
function chooseStart(key) {
  start.value = key
  if (key === 'template') applyTemplate()
  else if (key === 'blank') {
    form.value = blankForm(options.value)
    origin.value = null
  }
  // “用一句话描述”先保留当前表单，生成成功后再替换。
}

// ---------- 用一句话描述 ----------
const nlModel = ref({ ai: { available: false, model: null }, usage: null })
const nl = reactive({ description: '', generating: false, explanation: '', note: '' })
async function loadNlModel() {
  try { nlModel.value = await nlStatus() } catch (e) { props.notify(e.message || '加载模型状态失败') }
}
const nlModelText = computed(() => {
  const { ai, usage } = nlModel.value
  if (!ai.available) return '使用离线规则识别'
  const left = remainingText(usage, '生成') ? `，${remainingText(usage, '生成')}` : ''
  return `使用 AI 模型 ${ai.model}${left}`
})
async function generate() {
  if (!nl.description.trim()) return props.notify('请先写下策略的想法')
  nl.generating = true
  nl.explanation = ''
  nl.note = ''
  try {
    const result = await nlGenerate({
      description: nl.description,
      top_n: Number(form.value.top_n), rebalance: form.value.rebalance,
    })
    form.value = formFromDefinition(result.definition, form.value, options.value)
    origin.value = { kind: 'describe' }
    nl.explanation = result.explanation || ''
    nl.note = result.note || ''
    props.notify('规则已填进表单，请核对')
  } catch (e) {
    props.notify(e.message || '生成失败')
  } finally {
    nl.generating = false
    loadNlModel()
  }
}

// ---------- 表单 ----------
function addRule() {
  if (form.value.rules.length < MAX_RULES) form.value.rules.push(blankRule(options.value))
}
function removeRule(index) {
  if (form.value.rules.length > 1) form.value.rules.splice(index, 1)
}

// ---------- 这个策略的意思（由后端按将要执行的规则读出来） ----------
const check = reactive({ loading: false, description: '', warnings: [], minimumDays: null, error: '' })
let checkRequest = 0
let checkTimer = null
async function runCheck() {
  const request = ++checkRequest
  check.loading = true
  try {
    const payload = packagePayload(form.value, origin.value)
    // 名称不影响规则的含义；没填时用占位名，避免还没起名就看不到说明。
    if (!payload.definition.name) payload.definition.name = '未命名策略'
    const result = await preflightPackage(payload)
    if (request !== checkRequest) return
    Object.assign(check, { description: result.description || '', warnings: result.warnings || [], minimumDays: result.minimum_history_days ?? null, error: '' })
  } catch (e) {
    if (request === checkRequest) Object.assign(check, { description: '', warnings: [], minimumDays: null, error: e.message || '规则无法识别' })
  } finally {
    if (request === checkRequest) check.loading = false
  }
}
watch(form, () => {
  savedAsset.value = null
  clearTimeout(checkTimer)
  if (form.value) checkTimer = setTimeout(runCheck, 400)
}, { deep: true })

async function save() {
  if (!form.value.name.trim()) return props.notify('请先给策略起个名字')
  if (check.error) return props.notify('规则还有问题，请先按提示修改')
  saving.value = true
  try {
    savedAsset.value = await createPackage(packagePayload(form.value, origin.value))
    props.notify('策略已保存')
  } catch (e) {
    props.notify(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

watch(() => [tpl.template_id, tpl.style], () => { if (start.value === 'template' && options.value) applyTemplate() })
watch(() => props.routeContext.mode, (mode) => { if (mode && options.value) chooseStart(startFor(mode)) })
onMounted(async () => {
  try {
    options.value = await studioOptions()
    tpl.template_id = options.value.templates?.[0]?.template_id || ''
    form.value = blankForm(options.value)
    chooseStart(start.value)
  } catch (e) {
    loadError.value = e.message || '加载选项失败'
  }
  loadNlModel()
})
</script>

<template>
  <div class="space-y-6">
    <div class="glass relative overflow-hidden rounded-2xl p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-indigo-500/20 blur-3xl" />
      <h1 class="text-2xl font-bold text-white">新建规则策略</h1>
      <p class="mt-2 max-w-2xl text-sm text-slate-400">三种开始方式填的是同一张表单。保存的就是表单里看到的规则；保存后再到回测页配置日期、资金与风控。</p>
      <button class="mt-3 text-sm text-indigo-300 hover:text-indigo-200" @click="openResearch('strategy-hub')">← 返回我的策略</button>
    </div>

    <p v-if="loadError" class="text-sm text-rose-300" role="alert">{{ loadError }}</p>
    <div v-else-if="!form" class="text-sm text-slate-400" role="status">加载中…</div>
    <template v-else>
      <!-- 怎么开始 -->
      <SectionCard title="怎么开始？" hint="随时可以换一种方式，表单会跟着更新">
        <div class="grid gap-3 sm:grid-cols-3" role="group" aria-label="开始方式">
          <button v-for="item in STARTS" :key="item.key" type="button" :aria-pressed="start === item.key"
            class="rounded-xl border p-4 text-left transition"
            :class="start === item.key ? 'border-indigo-400/40 bg-indigo-500/20' : 'border-white/10 bg-white/5 hover:bg-white/10'"
            @click="chooseStart(item.key)">
            <span class="block text-sm font-semibold text-white">{{ item.label }}</span>
            <span class="mt-1 block text-xs text-slate-400">{{ item.hint }}</span>
          </button>
        </div>

        <div v-if="start === 'template'" class="mt-5">
          <div class="grid gap-4 sm:grid-cols-2">
            <FormField label="模板" type="select" v-model="tpl.template_id" :options="templateOptions" />
            <FormField label="风格" type="select" v-model="tpl.style" :options="styleOptions" />
          </div>
          <div v-if="currentTemplate" class="mt-4 rounded-xl border border-white/10 bg-white/5 p-4">
            <p class="text-sm text-slate-300">{{ currentTemplate.summary }}</p>
            <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
              <span class="text-slate-400">适合市场：{{ currentTemplate.suitable_market || '—' }}</span>
              <span class="text-amber-300">主要风险：{{ currentTemplate.main_risk || '—' }}</span>
            </div>
          </div>
        </div>

        <div v-else-if="start === 'describe'" class="mt-5 space-y-4">
          <FormField label="策略的想法" type="textarea" v-model="nl.description" :rows="3"
            placeholder="例如：5日均线高于20日均线并且放量时买入，按20日涨幅从强到弱选前5只" />
          <div class="flex flex-wrap items-center gap-3">
            <button type="button" :disabled="nl.generating" class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white transition hover:-translate-y-0.5 disabled:opacity-70" @click="generate">
              {{ nl.generating ? '生成中…' : '生成规则' }}
            </button>
            <span class="text-xs text-slate-400">{{ nlModelText }}。生成的规则会替换下面的表单，请核对后再保存。</span>
          </div>
          <p v-if="!nlModel.ai.available" class="text-xs text-amber-200">平台还没有配置 AI 模型，现在用离线规则识别，只能识别简单的句子，复杂的描述会漏掉条件。</p>
          <p v-if="nl.note" class="text-xs text-amber-200">{{ nl.note }}</p>
          <p v-if="nl.explanation" class="whitespace-pre-wrap rounded-xl border border-white/10 bg-white/5 p-4 text-sm leading-relaxed text-slate-300">{{ nl.explanation }}</p>
        </div>

        <p v-else class="mt-5 text-sm text-slate-400">下面的表单已经重置为一条空白条件，直接填写即可。</p>
      </SectionCard>

      <!-- 同一张表单 -->
      <SectionCard title="策略规则" hint="每个调仓日：先用条件筛选股票，再按排序取前几只，等权持有">
        <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <FormField label="策略名称" v-model="form.name" placeholder="如 动量 + 均线策略" />
          <FormField label="持股数量" type="number" v-model="form.top_n" :min="1" :max="50" :step="1" />
          <FormField label="调仓频率" type="select" v-model="form.rebalance" :options="freqOptions" />
          <FormField label="多条条件之间" type="select" v-model="form.entry_logic" :options="logicOptions" />
        </div>

        <h3 class="mt-6 text-sm font-semibold text-white">选股条件</h3>
        <p class="mt-1 text-xs text-slate-500">涨跌幅、回撤、波动率用小数填写：0.05 表示 5%。成交额的单位是元。</p>
        <ol class="mt-3 space-y-3" aria-label="选股条件">
          <li v-for="(rule, index) in form.rules" :key="index" class="rounded-xl border border-white/10 bg-white/5 p-4">
            <div class="flex items-center justify-between">
              <span class="text-xs text-slate-400">条件 {{ index + 1 }}</span>
              <button type="button" class="text-xs text-rose-300 hover:underline disabled:opacity-40" :disabled="form.rules.length <= 1" @click="removeRule(index)">删除</button>
            </div>
            <div class="mt-3 grid gap-4 md:grid-cols-2 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1.3fr)_minmax(0,1.3fr)_minmax(0,2fr)_minmax(0,1fr)]">
              <FormField label="指标" type="select" :model-value="rule.left.name" :options="indicatorOptions" @update:model-value="chooseIndicator(rule.left, $event, options)" />
              <FormField v-if="rule.left.window != null" label="周期（日）" type="number" v-model="rule.left.window" :min="windowLimits(rule.left.name).minimum" :max="windowLimits(rule.left.name).maximum" :step="1" />
              <div v-else class="hidden xl:block" />
              <FormField label="判断" type="select" v-model="rule.operator" :options="operatorOptions" />
              <FormField label="和什么比较" type="select" v-model="rule.compare" :options="compareOptions" />
              <template v-if="rule.compare === 'indicator'">
                <FormField label="另一个指标" type="select" :model-value="rule.right.name" :options="indicatorOptions" @update:model-value="chooseIndicator(rule.right, $event, options)" />
                <FormField v-if="rule.right.window != null" label="周期（日）" type="number" v-model="rule.right.window" :min="windowLimits(rule.right.name).minimum" :max="windowLimits(rule.right.name).maximum" :step="1" />
              </template>
              <FormField v-else label="数值" type="number" v-model="rule.value" step="any" />
            </div>
          </li>
        </ol>
        <button type="button" class="mt-3 text-sm text-indigo-300 hover:underline disabled:opacity-40" :disabled="form.rules.length >= MAX_RULES" @click="addRule">+ 添加条件</button>

        <h3 class="mt-6 text-sm font-semibold text-white">排序</h3>
        <div class="mt-3 grid gap-4 md:grid-cols-3">
          <FormField label="排序指标" type="select" :model-value="form.ranking.name" :options="indicatorOptions" @update:model-value="chooseIndicator(form.ranking, $event, options)" />
          <FormField v-if="form.ranking.window != null" label="周期（日）" type="number" v-model="form.ranking.window" :min="windowLimits(form.ranking.name).minimum" :max="windowLimits(form.ranking.name).maximum" :step="1" />
          <FormField label="排序方向" type="select" v-model="form.ranking.direction" :options="dirOptions" />
        </div>
      </SectionCard>

      <!-- 这个策略的意思 -->
      <SectionCard title="这个策略的意思" hint="按将要执行的规则读出来，随表单更新">
        <p v-if="check.error" class="text-sm text-rose-300" role="alert">{{ check.error }}</p>
        <p v-else-if="check.description" class="text-sm leading-relaxed text-slate-200" aria-live="polite">{{ check.description }}</p>
        <p v-else class="text-sm text-slate-400" role="status">正在读取…</p>
        <ul v-if="check.warnings.length" class="mt-3 space-y-1 rounded-xl border border-amber-400/20 bg-amber-400/5 p-4">
          <li v-for="(warning, index) in check.warnings" :key="index" class="text-xs text-amber-200">• {{ warning }}</li>
        </ul>
        <p v-if="check.minimumDays" class="mt-3 text-xs text-slate-500">至少需要 {{ check.minimumDays }} 个交易日的历史行情。</p>
        <div class="mt-5 flex flex-wrap items-center gap-3">
          <button type="button" :disabled="saving || check.loading || !!check.error" class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-5 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70" @click="save">
            {{ saving ? '保存中…' : '保存策略' }}
          </button>
          <span class="text-xs text-slate-400">保存不会运行回测。</span>
        </div>
      </SectionCard>

      <StrategySaved v-if="savedAsset" :asset="savedAsset" />
    </template>
  </div>
</template>
