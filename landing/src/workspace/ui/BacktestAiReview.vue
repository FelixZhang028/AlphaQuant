<script setup>
import { computed, ref, watch } from 'vue'
import { getBacktestReview, runBacktestReview } from '../../api.js'
import { openResearch } from '../researchNavigation.js'
import { factGroups, overfitText, percent, remainingText } from '../aiPresentation.js'
import { confidenceLabel, probabilityLabel } from '../jevReportPresentation.js'

const props = defineProps({
  backtestId: { type: [Number, String], default: null },
  notify: { type: Function, default: () => {} },
})

const state = ref(null) // { review, available, usage }
const running = ref(false)
const review = computed(() => state.value?.review || null)
const groups = computed(() => factGroups(review.value?.facts))
const left = computed(() => remainingText(state.value?.usage, '评估'))
const validityNotes = computed(() => (review.value?.facts || []).filter(fact => fact.key?.startsWith('issue_')))

async function load(id) {
  state.value = null
  if (!id) return
  try {
    const data = await getBacktestReview(id)
    if (String(id) === String(props.backtestId)) state.value = data
  } catch (e) {
    props.notify(e.message || '读取 AI 评估失败')
  }
}
watch(() => props.backtestId, load, { immediate: true })

async function run() {
  running.value = true
  try {
    state.value = await runBacktestReview(props.backtestId)
  } catch (e) {
    props.notify(e.message || 'AI 评估失败')
  } finally {
    running.value = false
  }
}
</script>

<template>
  <section v-if="state" class="rounded-xl border border-white/10 bg-white/5 p-4" aria-label="AI 评估">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h3 class="text-sm font-semibold text-white">AI 评估</h3>
        <p class="mt-0.5 text-xs text-slate-500">决策模型只根据这次回测自己的数字，估计风险有多高、结果在新数据上做不到的可能有多大</p>
      </div>
      <button v-if="!review && state.available" :disabled="running || state.usage?.remaining === 0"
        class="rounded-full border border-indigo-400/40 bg-indigo-500/10 px-4 py-2 text-sm font-medium text-indigo-200 transition hover:bg-indigo-500/20 disabled:opacity-60"
        @click="run">{{ running ? '评估中…' : '让 AI 评估这次回测' }}</button>
    </div>
    <p v-if="!review && !state.available" class="mt-3 text-sm text-amber-200">平台还没有配置决策模型，暂时不能评估。</p>
    <p v-else-if="!review && left" class="mt-2 text-xs text-slate-500">{{ left }}；评估过的回测再打开不会重复计数。</p>

    <template v-if="review">
      <div class="mt-4 rounded-xl border border-indigo-400/20 bg-indigo-500/5 p-4">
        <p class="text-xs text-slate-400">先看结论</p>
        <p class="mt-2 text-base leading-relaxed text-slate-200">本次回测的模型风险评级为<span class="font-semibold text-white">{{ review.risk.level }}</span>。{{ overfitText(review.overfit.probability) }}</p>
        <p class="mt-2 text-xs text-slate-500">这是对已有回测的判断，不是策略在未来赚钱的概率。</p>
      </div>
      <div v-if="validityNotes.length" class="mt-3 rounded-xl border border-amber-400/20 bg-amber-500/5 p-4">
        <p class="text-sm font-medium text-amber-200">先核查这些研究边界</p>
        <ul class="mt-2 space-y-1 text-xs leading-relaxed text-slate-400"><li v-for="fact in validityNotes" :key="fact.key">{{ fact.text }}</li></ul>
      </div>
      <div class="mt-4 grid gap-4 md:grid-cols-2">
        <div class="min-w-0">
          <p class="text-xs text-slate-400">风险等级</p>
          <p class="mt-1 text-lg font-semibold text-white">{{ review.risk.level }}</p>
          <p class="mt-1 text-xs text-slate-500">模型置信度 {{ probabilityLabel(review.risk.confidence) }}（{{ confidenceLabel(review.risk.confidence) }}）</p>
          <ul class="mt-2 space-y-1" aria-label="各等级的概率">
            <li v-for="(p, level) in review.risk.probabilities" :key="level" class="flex items-center gap-3 text-xs">
              <span class="w-16 shrink-0 text-slate-400">{{ level }}</span>
              <span class="h-1.5 flex-1 overflow-hidden rounded-full bg-white/10"><span class="block h-full rounded-full bg-indigo-400" :style="{ width: percent(p) }" /></span>
              <span class="w-10 shrink-0 text-right text-slate-400">{{ percent(p) }}</span>
            </li>
          </ul>
        </div>
        <div class="min-w-0">
          <p class="text-xs text-slate-400">在新数据上做不到的可能（过度拟合或巧合）</p>
          <p class="mt-1 text-lg font-semibold text-white">{{ percent(review.overfit.probability) }}</p>
          <p class="mt-1 text-xs text-slate-400">{{ overfitText(review.overfit.probability) }}</p>
          <button type="button" class="mt-2 text-xs text-indigo-300 hover:text-indigo-200" @click="openResearch('research', { baseline: `run-${backtestId}` })">用参数验证在样本外检查 →</button>
        </div>
      </div>
      <p class="mt-4 text-xs text-slate-500">这是模型根据下面这些数字给出的估计，不是保证；参数验证（样本外）比它更可靠。模型 {{ review.model }}</p>
      <details class="mt-2">
        <summary class="cursor-pointer text-xs text-slate-400">AI 看到的数据</summary>
        <div class="mt-2 grid gap-3 md:grid-cols-2">
          <dl v-for="group in groups" :key="group.group" class="min-w-0 space-y-1 text-xs">
            <dt class="font-semibold text-slate-300">{{ group.group }}</dt>
            <dd v-for="fact in group.items" :key="fact.key" class="flex flex-wrap justify-between gap-x-3 text-slate-400">
              <span>{{ fact.label }}</span><span class="text-slate-300" :class="fact.text.length > 24 ? 'w-full' : 'ml-auto text-right'">{{ fact.text }}</span>
            </dd>
          </dl>
        </div>
      </details>
    </template>
  </section>
</template>
