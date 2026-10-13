<script setup>
// 一组因子：常用的一组直接显示，Alpha101 这样的组折叠起来，标题上有数量和已选的个数。
defineProps({
  group: { type: Object, required: true }, // factorGroups() 里的一项
  open: { type: Boolean, default: false },
  selected: { type: Number, default: 0 },
})
defineEmits(['update:open'])
</script>

<template>
  <div v-if="!group.folded"><slot /></div>
  <details v-else class="mt-4 rounded-xl border border-white/10 bg-white/5 p-4" :open="open" @toggle="$emit('update:open', $event.target.open)">
    <summary class="cursor-pointer text-sm font-medium text-slate-200">
      {{ group.title }}（{{ group.factors.length }} 个<template v-if="selected">，已选 {{ selected }} 个</template>）
    </summary>
    <p class="mt-2 text-xs text-slate-400">{{ group.note }}</p>
    <div class="mt-3"><slot /></div>
  </details>
</template>
