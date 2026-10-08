<script setup>
import { computed } from 'vue'

const props = defineProps({
  value: { type: String, default: '' },
  text: { type: String, default: '' }, // 可选显示文本，缺省显示 value
})

const cls = computed(() => {
  const v = props.value
  if (['运行中', 'SUCCESS', '完成', '批准', '有效', 'VALID', '买入'].includes(v)) return 'text-emerald-300 bg-emerald-400/10 border-emerald-400/30'
  if (['已暂停', 'WARNING', '警告', '有条件批准', '持有'].includes(v)) return 'text-amber-300 bg-amber-400/10 border-amber-400/30'
  if (['已停止', 'FAILED', '失败', '拒绝', '卖出', 'INVALID'].includes(v)) return 'text-rose-300 bg-rose-400/10 border-rose-400/30'
  return 'text-slate-300 bg-white/5 border-white/10'
})
</script>

<template>
  <span class="inline-flex rounded-full border px-2.5 py-0.5 text-xs whitespace-nowrap" :class="cls">{{ text || value }}</span>
</template>
