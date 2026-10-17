<script setup>
import { onActivated, reactive, ref } from 'vue'
import { jevDecide, jevStatus } from '../../api.js'
import SectionCard from '../ui/SectionCard.vue'
import { remainingText } from '../aiPresentation.js'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

const status = ref(null)
const stateText = ref('')
function state() {
  const text = stateText.value.trim()
  if (!text) return {}
  try { const value = JSON.parse(text); return value === null || typeof value === 'object' || typeof value === 'string' ? value : text } catch { return text }
}
async function loadStatus() {
  try { status.value = await jevStatus() } catch (e) { props.notify(e.message) }
}
onActivated(loadStatus)
const activeTab = ref('choice')
const tabs = [
  { key: 'choice', label: '方案比较' },
  { key: 'noul', label: '条件判断' },
  { key: 'score', label: '等级评分' },
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
    loadStatus()
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
    loadStatus()
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
    loadStatus()
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
    <div class="glass glass-sheen rounded-2xl p-6">
      <h2 class="text-xl font-bold text-white">决策辅助</h2>
      <p class="mt-1 text-sm text-slate-400">
        提供研究材料，比较候选方案、判断条件或评估等级。结果用于辅助研究，不会执行交易。
      </p>
    </div>

    <p class="rounded-xl border border-white/10 p-4 text-sm" :class="status && !status.available ? 'text-amber-200' : 'text-slate-300'">
      <template v-if="!status">正在读取决策模型状态…</template>
      <template v-else-if="!status.available">平台还没有配置决策模型，暂时不能使用。</template>
      <template v-else>决策模型 {{ status.model }}{{ remainingText(status.usage, '使用') ? ' · ' + remainingText(status.usage, '使用') : '' }}</template>
    </p>
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
    <SectionCard v-if="activeTab === 'choice'" title="方案比较" subtitle="根据提供的材料比较候选方案，查看模型选择及各选项分布">
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
    <SectionCard v-if="activeTab === 'noul'" title="条件判断" subtitle="结合提供的材料，查看模型对条件成立的概率估计">
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
    <SectionCard v-if="activeTab === 'score'" title="等级评分" subtitle="在有序等级量表上给出评分，并映射到 0~100 分">
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
        <p v-if="result.confidence != null" class="text-xs text-slate-400">置信度 {{ pct(result.confidence) }}</p>

        <!-- Choice result -->
        <div v-if="result.selected !== undefined" class="space-y-3">
          <div class="rounded-lg border border-indigo-400/20 bg-indigo-500/5 p-4">
            <div class="text-xs text-slate-400">模型选择</div>
            <div class="mt-1 text-xl font-semibold text-indigo-200">{{ result.selected }}</div>
          </div>
          <div>
            <div class="mb-2 text-xs font-medium text-slate-400">模型选项分布</div>
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
            <div class="text-xs text-slate-400">模型估计的条件成立概率</div>
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
  </div>
</template>
