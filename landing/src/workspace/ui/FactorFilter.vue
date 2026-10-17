<script setup>
// 因子库的筛选条：按来源和类型两排，每一项后面是点下去以后的因子数。
import { computed } from 'vue'
import { filterOptions } from '../factorFilters.js'

const props = defineProps({
  factors: { type: Array, default: () => [] },
  modelValue: { type: Object, required: true }, // { source, type }，空字符串表示全部
})
const emit = defineEmits(['update:modelValue'])

const rows = computed(() => {
  const options = filterOptions(props.factors, props.modelValue)
  return [{ key: 'source', label: '来源', options: options.source }, { key: 'type', label: '类型', options: options.type }]
})
const choose = (key, value) => emit('update:modelValue', { ...props.modelValue, [key]: value })
</script>

<template>
  <div class="space-y-2">
    <div v-for="row in rows" :key="row.key" class="flex flex-wrap items-center gap-2" role="group" :aria-label="`按${row.label}筛选因子`">
      <span class="w-9 shrink-0 text-xs text-slate-400">{{ row.label }}</span>
      <button v-for="option in row.options" :key="option.value" type="button"
        :aria-pressed="modelValue[row.key] === option.value" :disabled="!option.count && modelValue[row.key] !== option.value"
        class="rounded-full border px-3 py-1 text-xs transition disabled:opacity-40"
        :class="modelValue[row.key] === option.value ? 'border-indigo-400/40 bg-indigo-500/20 text-indigo-200' : 'border-white/10 bg-white/5 text-slate-300 hover:bg-white/10'"
        @click="choose(row.key, option.value)">{{ option.label }} <span class="opacity-60">{{ option.count }}</span></button>
    </div>
  </div>
</template>
