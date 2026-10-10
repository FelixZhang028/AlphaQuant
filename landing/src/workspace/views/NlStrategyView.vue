<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { createPackage, nlGenerate, nlProviders } from '../../api.js'
import SectionCard from '../ui/SectionCard.vue'
import StrategySaved from '../ui/StrategySaved.vue'
import { openResearch } from '../researchNavigation.js'
import FormField from '../ui/FormField.vue'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

// ---------- 模型配置 ----------
const providers = ref([])
const loadingProviders = ref(false)

const form = reactive({
  provider: '',
  baseUrl: '',
  apiKey: '',
  model: '',
  description: '',
  top_n: 5,
  rebalance: 'weekly',
})

const rebalanceOptions = [
  { value: 'daily', label: '每日' },
  { value: 'weekly', label: '每周' },
  { value: 'monthly', label: '每月' },
]

const providerOptions = computed(() =>
  providers.value.map((p) => ({ value: p.key, label: p.display_name }))
)

const currentProvider = computed(() =>
  providers.value.find((p) => p.key === form.provider)
)

// requires_key=false 的服务商无需 API Key，禁用输入
const keyDisabled = computed(() => {
  const p = currentProvider.value
  return !!p && p.requires_key === false
})

const modelOptions = computed(() => currentProvider.value?.models || [])

function onProviderChange(key) {
  const p = providers.value.find((x) => x.key === key)
  if (!p) return
  form.baseUrl = p.default_base_url || ''
  form.model = p.default_model || (p.models && p.models.length ? p.models[0] : '')
}

async function loadProviders() {
  loadingProviders.value = true
  try {
    const data = await nlProviders()
    providers.value = data.providers || []
    if (providers.value.length) {
      form.provider = providers.value[0].key
      onProviderChange(form.provider)
    }
  } catch (e) {
    props.notify(e.message || '加载模型配置失败')
  } finally {
    loadingProviders.value = false
  }
}

// ---------- 生成策略规则 ----------
const generating = ref(false)
const saving = ref(false)
const savedAsset = ref(null)
const result = ref(null) // { definition, explanation, minimum_history_days }

const definitionJson = computed(() => {
  const d = result.value?.definition
  if (!d) return ''
  return JSON.stringify(d, null, 2)
})

async function onGenerate() {
  if (!form.description.trim()) return props.notify('请输入策略描述')
  if (!form.provider) return props.notify('请选择模型服务商')
  generating.value = true
  result.value = null
  try {
    result.value = await nlGenerate({
      description: form.description,
      provider: form.provider,
      base_url: form.baseUrl,
      api_key: form.apiKey,
      model: form.model,
      top_n: Number(form.top_n),
      rebalance: form.rebalance,
    })
  } catch (e) {
    props.notify(e.message || '生成失败')
  } finally {
    generating.value = false
  }
}

async function onSave() {
  if (!result.value?.definition) return
  saving.value = true
  try {
    savedAsset.value = await createPackage({
      definition: result.value.definition,
      top_n: Number(form.top_n),
      rebalance: form.rebalance,
      source: 'nl_builder',
    })
    props.notify('策略已保存')
  } catch (e) {
    props.notify(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadProviders)
</script>

<template>
  <div class="space-y-6">
    <!-- 标题 -->
    <div class="glass glass-sheen relative overflow-hidden rounded-2xl p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-indigo-500/20 blur-3xl" />
      <button class="mb-3 text-sm text-indigo-300" @click="openResearch('strategy-hub')">← 返回我的策略</button>
      <h1 class="text-xl font-bold text-white">自然语言建策略</h1>
      <p class="mt-2 max-w-xl text-sm text-slate-400">用一句话描述策略，大模型转成结构化规则</p>
    </div>

    <StrategySaved v-if="savedAsset" :asset="savedAsset" />

    <!-- 模型配置 -->
    <SectionCard title="模型配置" hint="选择用于生成策略规则的大模型服务">
      <div v-if="loadingProviders" class="text-sm text-slate-400">加载中…</div>
      <div v-else class="grid gap-4 sm:grid-cols-2">
        <FormField
          label="服务商"
          type="select"
          v-model="form.provider"
          :options="providerOptions"
          @update:modelValue="onProviderChange"
        />
        <FormField
          label="Base URL"
          v-model="form.baseUrl"
          placeholder="https://api.example.com/v1"
        />
        <div>
          <label class="mb-1 block text-xs text-slate-400">API Key</label>
          <input
            v-model="form.apiKey"
            type="password"
            :disabled="keyDisabled"
            placeholder="sk-..."
            class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40 disabled:opacity-50"
          />
          <p v-if="keyDisabled" class="mt-1 text-xs text-slate-500">该服务商无需 API Key</p>
        </div>
        <div>
          <label class="mb-1 block text-xs text-slate-400">模型</label>
          <input
            v-model="form.model"
            list="nl-strategy-models"
            placeholder="模型名称（可下拉或手填）"
            class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40"
          />
          <datalist id="nl-strategy-models">
            <option v-for="m in modelOptions" :key="m" :value="m" />
          </datalist>
        </div>
      </div>
    </SectionCard>

    <!-- 策略描述 -->
    <SectionCard title="策略描述" hint="用一句话描述交易想法，大模型会解析为可执行的结构化规则">
      <div class="space-y-4">
        <FormField
          label="策略描述"
          type="textarea"
          v-model="form.description"
          :rows="4"
          placeholder="例如：5日均线高于20日均线并且放量时买入，按20日涨幅从强到弱选前5只"
        />
        <div class="grid gap-4 sm:grid-cols-2">
          <FormField
            label="持股数量"
            type="number"
            v-model="form.top_n"
            :min="1"
            :max="50"
            :step="1"
          />
          <FormField
            label="调仓频率"
            type="select"
            v-model="form.rebalance"
            :options="rebalanceOptions"
          />
        </div>
        <div class="flex justify-end">
          <button
            @click="onGenerate"
            :disabled="generating"
            class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-6 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
          >
            {{ generating ? '生成中…' : '生成策略规则' }}
          </button>
        </div>
      </div>
    </SectionCard>

    <!-- 生成结果 -->
    <SectionCard v-if="result" title="生成结果（请核对）" hint="请仔细核对说明与结构化规则是否符合你的交易意图">
      <div class="rounded-xl border border-white/10 bg-white/5 p-4">
        <p class="text-xs text-slate-400">策略说明</p>
        <p class="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-300">
          {{ result.explanation || '（无说明）' }}
        </p>
        <p v-if="result.minimum_history_days" class="mt-3 text-xs text-slate-500">
          建议最少历史数据：{{ result.minimum_history_days }} 天
        </p>
      </div>

      <div class="mt-4">
        <p class="text-xs text-slate-400">结构化规则（JSON）</p>
        <pre
          class="mt-2 max-h-80 overflow-auto rounded-xl border border-white/10 bg-black/40 p-4 font-mono text-xs leading-relaxed text-slate-200"
        >{{ definitionJson }}</pre>
      </div>

      <div class="mt-4 flex justify-end">
        <button
          @click="onSave"
          :disabled="saving"
          class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-6 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
        >
          {{ saving ? '保存中…' : '确认并保存策略' }}
        </button>
      </div>
    </SectionCard>
  </div>
</template>
