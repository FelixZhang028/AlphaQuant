<script setup>
// 这组条件过去表现如何：用同样的选股条件回测最近几年，结果和普通回测一样保存，可以打开看完整结果。
import { computed, ref, watch } from 'vue'
import { screenHistory } from '../../api.js'
import { openResearch } from '../researchNavigation.js'
import { definitionFromForm } from '../ruleForm.js'
import { historyMetrics } from '../screenPresentation.js'
import FormField from './FormField.vue'
import SectionCard from './SectionCard.vue'

const props = defineProps({
  form: { type: Object, required: true },
  markets: { type: Array, default: () => [] },      // 筛选结果里带回来的回测范围（当前股票池、指数）
})

const market = ref('当前股票池')
const years = ref(1)
const topN = ref(5)
const rebalance = ref('weekly')
const running = ref(false)
const result = ref(null)
const stale = ref(false)
const error = ref('')

const marketOptions = computed(() => {
  const list = props.markets.length ? props.markets : [{ value: '当前股票池', label: '当前股票池', available: true }]
  return list.map((item) => ({ value: item.value, label: item.available ? item.label : `${item.label}（还没下载成分股）`, disabled: !item.available }))
})
const yearOptions = [{ value: 1, label: '最近 1 年' }, { value: 3, label: '最近 3 年' }, { value: 5, label: '最近 5 年' }]
const freqOptions = [{ value: 'daily', label: '每日' }, { value: 'weekly', label: '每周' }, { value: 'monthly', label: '每月' }]
const metrics = computed(() => historyMetrics(result.value?.summary))

watch(() => props.form, () => { if (result.value) stale.value = true }, { deep: true })

async function run() {
  running.value = true
  error.value = ''
  try {
    const definition = definitionFromForm(props.form)
    result.value = await screenHistory({ definition, market: market.value, years: Number(years.value), top_n: Number(topN.value), rebalance: rebalance.value })
    stale.value = false
  } catch (e) {
    error.value = e.message || '回测失败'
  } finally {
    running.value = false
  }
}
</script>

<template>
  <SectionCard title="这组条件过去表现如何" hint="用同样的选股条件回测：每个调仓日按条件选股、按排序取前几只、等权持有">
    <div class="flex flex-wrap items-end gap-4">
      <FormField class="min-w-[11rem] flex-[2]" label="在哪些股票里选" type="select" v-model="market" :options="marketOptions" />
      <FormField class="min-w-[8rem] flex-1" label="回测区间" type="select" :model-value="years" :options="yearOptions" @update:model-value="years = Number($event)" />
      <FormField class="w-28 shrink-0" label="持股数量" type="number" v-model="topN" :min="1" :max="50" :step="1" />
      <FormField class="min-w-[7rem] flex-1" label="调仓频率" type="select" v-model="rebalance" :options="freqOptions" />
      <button type="button" :disabled="running" class="rounded-full border border-indigo-400/40 bg-indigo-500/10 px-5 py-2.5 text-sm font-medium text-indigo-200 transition hover:bg-indigo-500/20 disabled:opacity-50" @click="run">
        {{ running ? '回测中…（几秒到一分钟）' : '回测这组条件' }}
      </button>
    </div>
    <p class="mt-2 text-xs text-slate-500">全市场太大，回测时请选股票池或指数（按当时的成分股，不会用今天的名单去回测过去）。历史表现不代表以后。</p>
    <p v-if="error" role="alert" class="mt-3 text-sm text-rose-300">{{ error }}</p>

    <div v-if="result" class="mt-4" aria-live="polite">
      <p v-if="stale" class="mb-2 text-xs text-amber-300">条件改过了，下面是改之前的回测；再点一次重新回测。</p>
      <dl class="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <div v-for="item in metrics" :key="item.label" class="rounded-xl border border-white/10 bg-white/5 p-3">
          <dt class="text-xs text-slate-400">{{ item.label }}</dt>
          <dd class="mt-1 text-lg font-semibold tabular-nums text-white">{{ item.value }}</dd>
        </div>
      </dl>
      <p v-if="result.summary && !result.summary.metrics_reliable" class="mt-2 text-xs text-amber-300">这次回测的数据或交易次数不够，指标仅供参考；打开完整结果可以看原因。</p>
      <button type="button" class="mt-3 text-sm text-indigo-300 hover:text-indigo-200" @click="openResearch('backtest-review', { run: result.id })">查看完整回测结果（收益曲线、交易记录、和基准对比）→</button>
    </div>
  </SectionCard>
</template>
