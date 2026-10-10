<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  createPackage,
  preflightPackage,
  studioOptions,
} from '../../api.js'
import StrategySaved from '../ui/StrategySaved.vue'
import { openResearch } from '../researchNavigation.js'
import SectionCard from '../ui/SectionCard.vue'
import FormField from '../ui/FormField.vue'

const props = defineProps({
  routeContext: { type: Object, default: () => ({}) },
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

const options = ref(null)
const activeTab = ref(props.routeContext.mode === 'builder' ? 'builder' : 'template')
const savedAsset = ref(null)
watch(() => props.routeContext.mode, (mode) => { activeTab.value = mode === 'builder' ? 'builder' : 'template' })
const tabs = [
  { key: 'template', label: '从模板创建' },
  { key: 'builder', label: '积木创建' },
]

// ---------- 选项映射 ----------
const freqOptions = [
  { value: 'daily', label: '每日' },
  { value: 'weekly', label: '每周' },
  { value: 'monthly', label: '每月' },
]
const dirOptions = [
  { value: 'descending', label: '降序' },
  { value: 'ascending', label: '升序' },
]
const styleOptions = [
  { value: 'conservative', label: '保守' },
  { value: 'balanced', label: '均衡' },
  { value: 'aggressive', label: '激进' },
]
const logicOptions = [
  { value: 'all', label: '全部满足' },
  { value: 'any', label: '任意满足' },
]

const templateOptions = computed(() =>
  (options.value?.templates || []).map((t) => ({ value: t.template_id, label: t.name }))
)
const indicatorOptions = computed(() => {
  const ind = options.value?.indicators || {}
  return Object.keys(ind).map((k) => ({ value: k, label: ind[k] }))
})
const operatorOptions = computed(() => {
  const op = options.value?.operators || {}
  return Object.keys(op).map((k) => ({ value: k, label: op[k] }))
})

// ---------- Tab 1：模板快速回测 ----------
const tpl = reactive({
  template_id: '',
  style: 'balanced',
  top_n: 10,
  rebalance: 'weekly',
  running: false,
})

const currentTemplate = computed(() =>
  (options.value?.templates || []).find((t) => t.template_id === tpl.template_id)
)

watch(
  () => tpl.template_id,
  (id) => {
    const t = (options.value?.templates || []).find((x) => x.template_id === id)
    if (t) {
      if (t.top_n != null) tpl.top_n = t.top_n
      if (t.rebalance) tpl.rebalance = t.rebalance
    }
  }
)

async function runTemplate() {
  if (!tpl.template_id) return props.notify('请选择模板')
  tpl.running = true
  try {
    const t = currentTemplate.value
    savedAsset.value = await createPackage({
      definition: {
        name: t.name,
        entry_logic: 'all',
        entry_rules: [],
        ranking: { indicator: { name: 'return_1d', window: 20 }, direction: 'descending' },
      },
      top_n: Number(tpl.top_n),
      rebalance: tpl.rebalance,
      source: `template:${tpl.template_id}`,
      style: tpl.style,
    })
    props.notify('模板策略已保存，请确认回测配置')
  } catch (e) {
    props.notify(e.message || '保存失败')
  } finally {
    tpl.running = false
  }
}

// ---------- Tab 2：积木创建 ----------
const bd = reactive({
  name: '',
  entry_logic: 'all',
  condition_count: 2,
  rules: Array.from({ length: 6 }, () => ({ indicator: '', operator: '', value: 0 })),
  ranking_indicator: '',
  ranking_direction: 'descending',
  top_n: 10,
  rebalance: 'weekly',
})
const bdWarnings = ref(null)
const bdChecking = ref(false)
const bdSaving = ref(false)

const conditionCount = computed(() => {
  const n = parseInt(bd.condition_count, 10)
  return Math.min(6, Math.max(1, Number.isNaN(n) ? 1 : n))
})

function buildBuilderPayload() {
  const entry_rules = bd.rules.slice(0, conditionCount.value).map((r) => ({
    left: { name: r.indicator },
    operator: r.operator,
    value: Number(r.value),
  }))
  return {
    definition: {
      name: bd.name,
      entry_logic: bd.entry_logic,
      entry_rules,
      ranking: { indicator: { name: bd.ranking_indicator }, direction: bd.ranking_direction },
    },
    top_n: Number(bd.top_n),
    rebalance: bd.rebalance,
    source: 'visual_builder',
  }
}

async function runPreflight() {
  if (!bd.name.trim()) return props.notify('请输入策略名称')
  bdChecking.value = true
  bdWarnings.value = null
  try {
    const res = await preflightPackage(buildBuilderPayload())
    bdWarnings.value = res
  } catch (e) {
    props.notify(e.message || '检查失败')
  } finally {
    bdChecking.value = false
  }
}

async function saveBuilder() {
  if (!bd.name.trim()) return props.notify('请输入策略名称')
  bdSaving.value = true
  try {
    savedAsset.value = await createPackage(buildBuilderPayload())
    props.notify('策略已保存')
    bd.name = ''
    bdWarnings.value = null
  } catch (e) {
    props.notify(e.message || '保存失败')
  } finally {
    bdSaving.value = false
  }
}

onMounted(async () => {
  try {
    options.value = await studioOptions()
    const indKeys = Object.keys(options.value.indicators || {})
    const opKeys = Object.keys(options.value.operators || {})
    bd.ranking_indicator = indKeys[0] || ''
    bd.rules = Array.from({ length: 6 }, () => ({
      indicator: indKeys[0] || '',
      operator: opKeys[0] || '',
      value: 0,
    }))
    if (options.value.templates?.length) tpl.template_id = options.value.templates[0].template_id
  } catch (e) {
    props.notify(e.message || '加载选项失败')
  }
})
</script>

<template>
  <div class="space-y-6">
    <!-- 标题 -->
    <div class="glass relative overflow-hidden rounded-2xl p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-indigo-500/20 blur-3xl" />
      <p class="text-sm text-slate-400">策略研究</p>
      <h1 class="mt-1 text-2xl font-bold text-white">创建规则策略</h1>
      <button class="mt-3 text-sm text-indigo-300 hover:text-indigo-200" @click="openResearch('strategy-hub')">← 返回我的策略</button>
      <p class="mt-2 max-w-2xl text-sm text-slate-400">选择模板或搭建规则，保存后到统一回测页配置日期、资金与风控。</p>
    </div>

    <StrategySaved v-if="savedAsset" :asset="savedAsset" />

    <!-- 分段按钮 Tab -->
    <div class="flex w-fit rounded-full border border-white/10 bg-white/5 p-0.5 text-xs">
      <button
        v-for="t in tabs"
        :key="t.key"
        @click="openResearch('strategy-studio', { mode: t.key })"
        class="rounded-full px-3 py-1 transition"
        :class="activeTab === t.key ? 'bg-gradient-to-r from-indigo-500 to-violet-500 text-white' : 'text-slate-400 hover:text-slate-200'"
      >
        {{ t.label }}
      </button>
    </div>

    <!-- Tab 1：模板快速回测 -->
    <template v-if="activeTab === 'template'">
      <div v-if="!options" class="text-sm text-slate-400">加载中…</div>
      <template v-else>
        <SectionCard title="从模板创建" hint="先保存策略，回测不会自动执行">
          <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <FormField label="模板" type="select" v-model="tpl.template_id" :options="templateOptions" />
            <FormField label="风格" type="select" v-model="tpl.style" :options="styleOptions" />
            <FormField label="持股数量" type="number" v-model="tpl.top_n" :min="1" :max="50" />
            <FormField label="调仓频率" type="select" v-model="tpl.rebalance" :options="freqOptions" />
          </div>

          <div v-if="currentTemplate" class="mt-4 rounded-xl border border-white/10 bg-white/5 p-4">
            <p class="text-sm text-slate-300">{{ currentTemplate.summary }}</p>
            <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
              <span class="text-slate-400">适合市场：{{ currentTemplate.suitable_market || '—' }}</span>
              <span class="text-amber-300">主要风险：{{ currentTemplate.main_risk || '—' }}</span>
              <span class="text-slate-400">风格：{{ styleOptions.find((s) => s.value === tpl.style)?.label || '—' }}</span>
            </div>
          </div>

          <button
            @click="runTemplate"
            :disabled="tpl.running"
            class="mt-5 rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
          >
            {{ tpl.running ? '保存中…' : '保存模板策略' }}
          </button>
        </SectionCard>

      </template>
    </template>

    <!-- Tab 2：积木创建 -->
    <template v-else-if="activeTab === 'builder'">
      <div v-if="!options" class="text-sm text-slate-400">加载中…</div>
      <template v-else>
        <SectionCard title="积木创建" hint="用条件积木搭建策略规则，生成并检查后保存">
          <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <FormField label="策略名称" v-model="bd.name" placeholder="如 动量 + 均线策略" />
            <FormField label="条件组合" type="select" v-model="bd.entry_logic" :options="logicOptions" />
            <FormField label="条件数量（1-6）" type="number" v-model="bd.condition_count" :min="1" :max="6" />
            <FormField label="持股数量" type="number" v-model="bd.top_n" :min="1" :max="50" />
          </div>

          <div class="mt-4 space-y-3">
            <div
              v-for="i in conditionCount"
              :key="i"
              class="rounded-xl border border-white/10 bg-white/5 p-4"
            >
              <p class="text-xs text-slate-400">条件 {{ i }}</p>
              <div class="mt-3 grid gap-4 md:grid-cols-3">
                <FormField label="指标" type="select" v-model="bd.rules[i - 1].indicator" :options="indicatorOptions" />
                <FormField label="判断" type="select" v-model="bd.rules[i - 1].operator" :options="operatorOptions" />
                <FormField label="比较数值" type="number" v-model="bd.rules[i - 1].value" :step="0.01" />
              </div>
            </div>
          </div>

          <div class="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <FormField label="排序指标" type="select" v-model="bd.ranking_indicator" :options="indicatorOptions" />
            <FormField label="排序方向" type="select" v-model="bd.ranking_direction" :options="dirOptions" />
            <FormField label="调仓频率" type="select" v-model="bd.rebalance" :options="freqOptions" />
          </div>

          <div v-if="bdWarnings" class="mt-4 rounded-xl border border-amber-400/20 bg-amber-400/5 p-4">
            <p class="text-xs text-amber-300">
              检查结果：{{ bdWarnings.warnings?.length ? `${bdWarnings.warnings.length} 条提示` : '未发现明显问题' }}
            </p>
            <ul v-if="bdWarnings.warnings?.length" class="mt-2 space-y-1">
              <li v-for="(w, i) in bdWarnings.warnings" :key="i" class="text-xs text-slate-300">• {{ w }}</li>
            </ul>
            <p v-if="bdWarnings.minimum_history_days" class="mt-2 text-xs text-slate-500">
              建议最低历史数据：{{ bdWarnings.minimum_history_days }} 天
            </p>
          </div>

          <div class="mt-5 flex flex-wrap gap-3">
            <button
              @click="runPreflight"
              :disabled="bdChecking"
              class="rounded-full border border-white/10 px-4 py-2 text-sm text-slate-300 transition hover:bg-white/5 disabled:opacity-70"
            >
              {{ bdChecking ? '检查中…' : '生成并检查策略' }}
            </button>
            <button
              @click="saveBuilder"
              :disabled="bdSaving"
              class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
            >
              {{ bdSaving ? '保存中…' : '保存策略' }}
            </button>
          </div>
        </SectionCard>
      </template>
    </template>

  </div>
</template>
