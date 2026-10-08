<script setup>
defineProps({ text: { type: String, default: '暂无数据' } })
</script>

<template>
  <div class="rounded-xl border border-dashed border-white/10 p-8 text-center text-sm text-slate-500">{{ text }}</div>
</template>
