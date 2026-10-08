<script setup>
import { onActivated, reactive, ref } from 'vue'
import { jevDecide, jevSettings, jevSaveSettings } from '../../api.js'
import SectionCard from '../ui/SectionCard.vue'

const props = defineProps({
  settingsOnly: { type: Boolean, default: false },
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

const configured = ref(false)
const saving = ref(false)
const showConfig = ref(false)
const config = reactive({ base_url: 'https://openrouter.ai/api/alpha/decisions', api_key: '', model: 'typesafe/jev-1.13' })
const stateText = ref('')
function state() {
  const text = stateText.value.trim()
  if (!text) return {}
  try { const value = JSON.parse(text); return value === null || typeof value === 'object' || typeof value === 'string' ? value : text } catch { return text }
}
async function loadSettings() {
  const data = await jevSettings()
  configured.value = data.configured
  config.base_url = data.base_url
  config.model = data.model
}
onActivated(async () => { try { await loadSettings() } catch (e) { props.notify(e.message) } })
async function saveSettings() {
  saving.value = true
  try { await jevSaveSettings(config); config.api_key = ''; await loadSettings(); showConfig.value = false; props.notify('Jev 配置已保存') }
  catch (e) { props.notify(e.message) } finally { saving.value = false }
}
const activeTab = ref('choice')
const tabs = [
  { key: 'choice', label: 'Choice 选项决策' },
  { key: 'noul', label: 'Noul 条件判断' },
  { key: 'score', label: 'Score 量表评分' },
]

const loading = ref(false)
const result = ref(null)

// ---- Choice ----
const choiceForm = reactive({
  question: '当前市场环境下应选择哪种策略风格？',
  options: ['动量策略', '均值回归', '多因子选股', '低波动防御'],
})

async function runChoice() {
  if (!choiceForm.options.length) {
    props.notify('请至少填写一个选项')
    return
  }
  loading.value = true
  result.value = null
  try {
    result.value = await jevDecide({
      type: 'choice',
      state: state(),
      question: choiceForm.question,
      options: choiceForm.options,
    })
  } catch (e) {
    props.notify(e.message || '决策请求失败')
  } finally {
    loading.value = false
  }
}

// ---- Noul ----
const noulForm = reactive({
  condition: '未来一个月沪深300指数会上涨',
})

async function runNoul() {
  if (!noulForm.condition.trim()) {
    props.notify('请填写要判断的条件')
    return
  }
  loading.value = true
  result.value = null
  try {
    result.value = await jevDecide({
      type: 'noul',
      state: state(),
      condition: noulForm.condition,
    })
  } catch (e) {
    props.notify(e.message || '决策请求失败')
  } finally {
    loading.value = false
  }
}

// ---- Score ----
const scoreForm = reactive({
  question: '该策略的风险等级评估',
  levels: ['低风险', '中低风险', '中等风险', '中高风险', '高风险'],
})

async function runScore() {
  if (!scoreForm.levels.length) {
    props.notify('请至少填写一个等级')
    return
  }
  loading.value = true
  result.value = null
  try {
    result.value = await jevDecide({
      type: 'score',
      state: state(),
      question: scoreForm.question,
      levels: scoreForm.levels,
    })
  } catch (e) {
    props.notify(e.message || '决策请求失败')
  } finally {
    loading.value = false
  }
}

function addOption() {
  choiceForm.options.push('')
}
function removeOption(i) {
  choiceForm.options.splice(i, 1)
}
function addLevel() {
  scoreForm.levels.push('')
}
function removeLevel(i) {
  scoreForm.levels.splice(i, 1)
}

function pct(v) {
  return typeof v === 'number' && isFinite(v) ? (v * 100).toFixed(1) + '%' : '—'
}
function score0100(r) {
  if (!r || !r.levels || r.levels.length <= 1) return '—'
  const n = r.levels.length
  return ((r.score / (n - 1)) * 100).toFixed(1)
}
</script>

<template>
  <div class="space-y-5">
    <div>
      <h1 class="text-2xl font-semibold text-white">AI 决策中心</h1>
      <p class="mt-1 text-sm text-slate-400">
        基于 Jev 结构化决策模型，提供 Choice（选项决策）、Noul（条件判断）、Score（量表评分）三种决策原语。未配置 OpenRouter 时自动使用离线演示模式。
      </p>
    </div>

    <div class="flex items-center justify-between rounded-xl border border-white/10 p-4 text-sm text-slate-300">
      <span>{{ configured ? 'Jev 已配置，执行时调用真实服务' : '演示模式：尚未配置 OpenRouter API Key' }}</span>
      <button @click="showConfig = !showConfig" class="rounded-lg border border-white/10 px-3 py-1">配置</button>
    </div>
    <SectionCard v-if="showConfig || settingsOnly" title="Jev 服务配置">
      <form class="space-y-3" @submit.prevent="saveSettings">
        <label class="block text-xs text-slate-400">决策服务地址<input v-model="config.base_url" class="mt-1 w-full rounded-lg border border-white/10 bg-ink/60 p-3 text-sm text-white" /></label>
        <label class="block text-xs text-slate-400">模型<input v-model="config.model" class="mt-1 w-full rounded-lg border border-white/10 bg-ink/60 p-3 text-sm text-white" /></label>
        <label class="block text-xs text-slate-400">OpenRouter API Key<input v-model="config.api_key" type="password" autocomplete="new-password" placeholder="留空保留已保存的 Key" class="mt-1 w-full rounded-lg border border-white/10 bg-ink/60 p-3 text-sm text-white" /></label>
        <button :disabled="saving" class="rounded-lg bg-indigo-500 px-4 py-2 text-sm text-white disabled:opacity-50">{{ saving ? '保存中…' : '保存配置' }}</button>
      </form>
    </SectionCard>
    <template v-if="!settingsOnly">
    <SectionCard title="决策上下文" subtitle="填写供模型判断的事实、行情或研究材料（文本或 JSON）">
      <textarea v-model="stateText" aria-label="决策上下文" rows="4" placeholder="例如：市场近20日涨幅、波动率、策略回测摘要" class="w-full rounded-lg border border-white/10 bg-ink/60 p-3 text-sm text-white" />
    </SectionCard>
    <!-- Tabs -->
    <div class="flex gap-1 rounded-xl border border-white/10 bg-white/5 p-1">
      <button
        v-for="t in tabs"
        :key="t.key"
        @click="activeTab = t.key; result = null" :disabled="loading"
        :class="[
          'flex-1 rounded-lg px-3 py-2 text-sm font-medium transition',
          activeTab === t.key ? 'bg-indigo-500/20 text-indigo-200' : 'text-slate-400 hover:text-slate-200',
        ]"
      >
        {{ t.label }}
      </button>
    </div>

    <!-- Choice -->
    <SectionCard v-if="activeTab === 'choice'" title="Choice 选项决策" subtitle="在多个候选选项中选择最优项，并给出各选项概率分布">
      <div class="space-y-4">
        <div>
          <label class="mb-1.5 block text-xs font-medium text-slate-400">决策问题</label>
          <input
            v-model="choiceForm.question"
            class="w-full rounded-lg border border-white/10 bg-ink/60 px-3 py-2 text-sm text-slate-100 outline-none focus:border-indigo-400/50"
            placeholder="描述你要决策的问题"
          />
        </div>
        <div>
          <div class="mb-1.5 flex items-center justify-between">
            <label class="text-xs font-medium text-slate-400">候选选项</label>
            <button @click="addOption" class="text-xs text-indigo-300 hover:text-indigo-200">+ 添加选项</button>
          </div>
          <div class="space-y-2">
            <div v-for="(opt, i) in choiceForm.options" :key="i" class="flex gap-2">
              <input
                v-model="choiceForm.options[i]"
                class="flex-1 rounded-lg border border-white/10 bg-ink/60 px-3 py-2 text-sm text-slate-100 outline-none focus:border-indigo-400/50"
                :placeholder="`选项 ${i + 1}`"
              />
              <button
                v-if="choiceForm.options.length > 1"
                @click="removeOption(i)"
                class="rounded-lg border border-white/10 px-3 text-slate-400 hover:border-rose-400/40 hover:text-rose-300"
              >
                移除
              </button>
            </div>
          </div>
        </div>
        <button
          @click="runChoice"
          :disabled="loading"
          class="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-400 disabled:opacity-50"
        >
          {{ loading ? '决策中…' : '运行决策' }}
        </button>
      </div>
    </SectionCard>

    <!-- Noul -->
    <SectionCard v-if="activeTab === 'noul'" title="Noul 条件判断" subtitle="判断某个条件成立的概率（0~1）">
      <div class="space-y-4">
        <div>
          <label class="mb-1.5 block text-xs font-medium text-slate-400">待判断条件</label>
          <textarea
            v-model="noulForm.condition"
            rows="3"
            class="w-full rounded-lg border border-white/10 bg-ink/60 px-3 py-2 text-sm text-slate-100 outline-none focus:border-indigo-400/50"
            placeholder="例如：未来一周市场波动率会显著上升"
          />
        </div>
        <button
          @click="runNoul"
          :disabled="loading"
          class="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-400 disabled:opacity-50"
        >
          {{ loading ? '判断中…' : '运行判断' }}
        </button>
      </div>
    </SectionCard>

    <!-- Score -->
    <SectionCard v-if="activeTab === 'score'" title="Score 量表评分" subtitle="在有序等级量表上给出评分，并映射到 0~100 分">
      <div class="space-y-4">
        <div>
          <label class="mb-1.5 block text-xs font-medium text-slate-400">评分问题</label>
          <input
            v-model="scoreForm.question"
            class="w-full rounded-lg border border-white/10 bg-ink/60 px-3 py-2 text-sm text-slate-100 outline-none focus:border-indigo-400/50"
            placeholder="描述你要评分的对象"
          />
        </div>
        <div>
          <div class="mb-1.5 flex items-center justify-between">
            <label class="text-xs font-medium text-slate-400">有序等级（从低到高）</label>
            <button @click="addLevel" class="text-xs text-indigo-300 hover:text-indigo-200">+ 添加等级</button>
          </div>
          <div class="space-y-2">
            <div v-for="(lv, i) in scoreForm.levels" :key="i" class="flex items-center gap-2">
              <span class="w-6 text-center text-xs text-slate-500">{{ i + 1 }}</span>
              <input
                v-model="scoreForm.levels[i]"
                class="flex-1 rounded-lg border border-white/10 bg-ink/60 px-3 py-2 text-sm text-slate-100 outline-none focus:border-indigo-400/50"
                :placeholder="`等级 ${i + 1}`"
              />
              <button
                v-if="scoreForm.levels.length > 1"
                @click="removeLevel(i)"
                class="rounded-lg border border-white/10 px-3 text-slate-400 hover:border-rose-400/40 hover:text-rose-300"
              >
                移除
              </button>
            </div>
          </div>
        </div>
        <button
          @click="runScore"
          :disabled="loading"
          class="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-400 disabled:opacity-50"
        >
          {{ loading ? '评分中…' : '运行评分' }}
        </button>
      </div>
    </SectionCard>

    <!-- Result -->
    <SectionCard v-if="result" title="决策结果">
      <div class="space-y-4">
        <div class="flex items-center gap-2">
          <span
            :class="[
              'rounded-full px-2 py-0.5 text-xs font-medium',
              result.mock ? 'bg-amber-500/15 text-amber-300' : 'bg-emerald-500/15 text-emerald-300',
            ]"
          >
            {{ result.mock ? '演示模式（Mock）' : '真实模型' }}
          </span>
          <span v-if="result.confidence != null" class="text-xs text-slate-400">置信度 {{ pct(result.confidence) }}</span>
        </div>

        <!-- Choice result -->
        <div v-if="result.selected !== undefined" class="space-y-3">
          <div class="rounded-lg border border-indigo-400/20 bg-indigo-500/5 p-4">
            <div class="text-xs text-slate-400">最优选择</div>
            <div class="mt-1 text-xl font-semibold text-indigo-200">{{ result.selected }}</div>
          </div>
          <div>
            <div class="mb-2 text-xs font-medium text-slate-400">各选项概率</div>
            <div class="space-y-2">
              <div v-for="(p, opt) in result.probabilities" :key="opt" class="flex items-center gap-3">
                <span class="w-32 truncate text-sm text-slate-300">{{ opt }}</span>
                <div class="h-2 flex-1 overflow-hidden rounded-full bg-white/5">
                  <div
                    class="h-full rounded-full bg-indigo-400"
                    :style="{ width: (p * 100).toFixed(1) + '%' }"
                  />
                </div>
                <span class="w-14 text-right text-xs text-slate-400">{{ pct(p) }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Noul result -->
        <div v-else-if="result.probability !== undefined" class="space-y-3">
          <div class="rounded-lg border border-indigo-400/20 bg-indigo-500/5 p-4">
            <div class="text-xs text-slate-400">条件成立概率</div>
            <div class="mt-1 text-3xl font-semibold text-indigo-200">{{ pct(result.probability) }}</div>
          </div>
          <div class="h-2 overflow-hidden rounded-full bg-white/5">
            <div
              class="h-full rounded-full"
              :class="result.probability >= 0.5 ? 'bg-emerald-400' : 'bg-rose-400'"
              :style="{ width: (result.probability * 100).toFixed(1) + '%' }"
            />
          </div>
        </div>

        <!-- Score result -->
        <div v-else-if="result.score !== undefined" class="space-y-3">
          <div class="rounded-lg border border-indigo-400/20 bg-indigo-500/5 p-4">
            <div class="flex items-end justify-between">
              <div>
                <div class="text-xs text-slate-400">综合评分（0-100）</div>
                <div class="mt-1 text-3xl font-semibold text-indigo-200">{{ score0100(result) }}</div>
              </div>
              <div class="text-right">
                <div class="text-xs text-slate-400">量表位置</div>
                <div class="mt-1 text-lg text-slate-200">
                  {{ result.score.toFixed(2) }} / {{ result.levels.length - 1 }}
                </div>
              </div>
            </div>
          </div>
          <div class="space-y-2">
            <div v-for="(p, lv) in result.level_probabilities" :key="lv" class="flex items-center gap-3">
              <span class="w-28 truncate text-sm text-slate-300">{{ lv }}</span>
              <div class="h-2 flex-1 overflow-hidden rounded-full bg-white/5">
                <div
                  class="h-full rounded-full bg-indigo-400"
                  :style="{ width: (p * 100).toFixed(1) + '%' }"
                />
              </div>
              <span class="w-14 text-right text-xs text-slate-400">{{ pct(p) }}</span>
            </div>
          </div>
        </div>
      </div>
    </SectionCard>
    </template>
  </div>
</template>
