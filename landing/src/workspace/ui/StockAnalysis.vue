<script setup>
// 短期分析 / 长期分析：把下面各节的数据按规则整理成几条话，每条后面可以跳到依据。
// 短期里“历史上类似的情况”用事件研究现算（截止到分析那一天，不用之后的数据）。
import { computed, ref, watch } from 'vue'
import { runEventStudy } from '../../api.js'
import { openResearch } from '../researchNavigation.js'
import { encodePreset, statesFromFacts } from '../eventStudy.js'
import { longAnalysis, shortAnalysis } from '../stockAnalysis.js'
import SectionCard from './SectionCard.vue'

const props = defineProps({
  report: { type: Object, required: true },
  facts: { type: Array, default: () => [] },
  tradeDate: { type: String, default: '' },
})

const states = computed(() => statesFromFacts(props.facts))
const study = ref(null)
let asked = 0
async function ask(state) {
  const mine = ++asked
  study.value = { loading: true, label: state.text, state }
  try {
    const result = await runEventStudy({ conditions: state.conditions, end: props.tradeDate || '' })
    if (mine === asked) study.value = { result, label: state.text, state }
  } catch (e) {
    if (mine === asked) study.value = { error: e.message || '统计没有完成', label: state.text, state }
  }
}
watch(() => [props.tradeDate, states.value[0]?.text], () => { if (states.value[0]) ask(states.value[0]); else study.value = null }, { immediate: true })

const short = computed(() => shortAnalysis(props.report, study.value))
const long = computed(() => longAnalysis(props.report))
const columns = computed(() => [
  { key: 'short', title: '短期分析', span: '几天到一个月', items: short.value },
  { key: 'long', title: '长期分析', span: '一年以上', items: long.value },
])

function follow(item) {
  if (item.target === 'event-study') {
    if (study.value?.state) openResearch('event-study', { preset: encodePreset(study.value.state.conditions) })
    return
  }
  document.getElementById(item.target)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
</script>

<template>
  <SectionCard title="短期分析 · 长期分析" hint="根据本地数据和历史统计整理，只描述数据，不是投资建议">
    <div class="grid gap-4 lg:grid-cols-2">
      <section v-for="column in columns" :key="column.key" class="min-w-0 rounded-xl border border-white/10 bg-white/[0.03] p-4">
        <h3 class="text-sm font-semibold text-white">{{ column.title }} <span class="text-xs font-normal text-slate-500">{{ column.span }}</span></h3>
        <ul class="mt-3 space-y-4">
          <li v-for="item in column.items" :key="item.key">
            <p class="text-xs font-semibold text-slate-400">{{ item.title }}</p>
            <p class="mt-0.5 text-sm leading-relaxed text-slate-200" :class="{ 'text-slate-400': item.key === 'history' && study?.loading }" :role="item.key === 'history' ? 'status' : undefined">{{ item.text }}</p>
            <p class="mt-0.5 flex flex-wrap items-center gap-x-3 text-xs text-slate-500">
              <span v-if="item.basis">{{ item.basis }}</span>
              <button v-if="item.target !== 'event-study' || study?.result" type="button" class="text-indigo-300 hover:text-indigo-200" @click="follow(item)">{{ item.target === 'event-study' ? '在事件研究里看 →' : '依据 →' }}</button>
            </p>
            <div v-if="item.key === 'history' && states.length > 1" class="mt-2 flex flex-wrap items-center gap-1.5">
              <span class="text-xs text-slate-500">也可以看：</span>
              <button v-for="state in states.slice(1)" :key="state.text" type="button"
                class="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-300 transition hover:border-indigo-400/40 hover:text-white"
                :class="{ 'border-indigo-400/50 text-white': study?.state?.text === state.text }" @click="ask(state)">{{ state.text }}</button>
              <button v-if="study?.state?.text !== states[0].text" type="button" class="text-xs text-indigo-300 hover:text-indigo-200" @click="ask(states[0])">回到“{{ states[0].text }}”</button>
            </div>
          </li>
        </ul>
      </section>
    </div>
  </SectionCard>
</template>
