<script setup>
// AI 解读这组股票：排序前 30 只的共同特征、明显不同的几只、风险线索、接下来核查什么。
// 每条要点下面列出它依据的本地数据；不给股票排名。同一组条件、同一天再看不重复扣次数。
import { computed, ref, watch } from 'vue'
import { screenBrief } from '../../api.js'
import { canUse, evidenceText, useLabel } from '../aiPresentation.js'

const props = defineProps({
  request: { type: Object, required: true },   // 刚才筛选用的 { definition, scope, exclude_st }
  result: { type: Object, required: true },    // 筛选结果（里面有 ai.available、ai.usage）
  stale: { type: Boolean, default: false },
})

const SECTIONS = [
  { key: 'common_points', label: '共同特征' },
  { key: 'outlier_points', label: '明显不同的几只' },
  { key: 'risk_points', label: '风险线索' },
  { key: 'check_points', label: '接下来可以核查' },
]
const reading = ref(null)
const usage = ref(props.result.ai?.usage || null)
const running = ref(false)
const error = ref('')

// 换了一组结果：之前的解读不再对应，收起来
watch(() => props.result, (value) => { reading.value = null; error.value = ''; usage.value = value.ai?.usage || null })

const stocks = computed(() => Math.min(props.result.matched, props.result.ai?.stocks || 30))
const buttonText = computed(() => useLabel(usage.value, `AI 解读这组股票（排序前 ${stocks.value} 只）`))

async function run() {
  running.value = true
  error.value = ''
  try {
    const data = await screenBrief(props.request)
    reading.value = data
    usage.value = data.usage || usage.value
  } catch (e) {
    error.value = e.message || 'AI 解读失败'
  } finally {
    running.value = false
  }
}
</script>

<template>
  <div class="mt-5 rounded-xl border border-indigo-400/20 bg-indigo-500/5 p-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h3 class="text-sm font-semibold text-white">AI 解读这组股票</h3>
        <p class="mt-0.5 text-xs text-slate-500">看这组条件筛出了一批什么样的股票：共同特征、明显不同的几只、风险线索。只用本地数据，不给股票排名。</p>
      </div>
      <button v-if="result.ai?.available && !reading" type="button" :disabled="running || stale || !canUse(usage)"
        class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white transition hover:-translate-y-0.5 disabled:opacity-50"
        @click="run">{{ running ? 'AI 解读中…（十几秒）' : buttonText }}</button>
    </div>
    <p v-if="!result.ai?.available" class="mt-3 text-sm text-slate-400">平台还没有配置文本模型，暂时不能解读。</p>
    <p v-else-if="stale && !reading" class="mt-3 text-xs text-amber-300">条件改过了，先重新筛选再解读。</p>
    <p v-if="error" role="alert" class="mt-3 text-sm text-rose-300">{{ error }}</p>

    <div v-if="reading" class="mt-4" aria-live="polite">
      <p class="text-xs text-slate-500">
        按 {{ reading.trade_date }} 的数据，解读了排序前 {{ reading.stocks }} 只 · 模型 {{ reading.model }}
        <span v-if="reading.cached"> · 这是今天保存的解读，没有再扣次数</span>
      </p>
      <p v-if="reading.brief.summary" class="mt-3 text-sm leading-relaxed text-slate-100">{{ reading.brief.summary }}</p>
      <div class="mt-4 grid gap-4 lg:grid-cols-2">
        <div v-for="section in SECTIONS" :key="section.key" class="min-w-0 rounded-xl border border-white/10 bg-white/5 p-4">
          <h4 class="text-xs font-semibold text-slate-300">{{ section.label }}</h4>
          <p v-if="!reading.brief[section.key]?.length" class="mt-2 text-sm text-slate-500">没有</p>
          <ul v-else class="mt-2 space-y-3">
            <li v-for="(point, i) in reading.brief[section.key]" :key="i">
              <p class="text-sm leading-relaxed text-slate-200">{{ point.text }}</p>
              <details v-if="point.evidence.length" class="mt-1 text-xs text-slate-500">
                <summary class="w-fit cursor-pointer">依据（{{ point.evidence.length }} 项）</summary>
                <p v-for="fact in point.evidence" :key="fact.key" class="mt-1">{{ evidenceText(fact, reading.trade_date) }}</p>
              </details>
            </li>
          </ul>
        </div>
      </div>
      <p v-if="reading.brief.removed" class="mt-3 text-xs text-slate-500">已去掉 {{ reading.brief.removed }} 条与数据对不上、没有依据、给出买卖建议或说价格方向的内容。</p>
      <p class="mt-2 text-xs text-slate-500">AI 只是归纳这组数据，可能出错，也不构成投资建议；想细看哪一只，点表格里的“AI 分析”。</p>
    </div>
  </div>
</template>
