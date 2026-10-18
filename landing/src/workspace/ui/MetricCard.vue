<script setup>
defineProps({
  label: { type: String, default: '' },
  value: { type: [String, Number], default: '—' },
  sub: { type: String, default: '' },
  up: { type: Boolean, default: null },
  tone: { type: String, default: '' }, // text-emerald-300 / text-rose-300 / text-indigo-300 ...
})
</script>

<template>
  <div class="glass glass-sheen rounded-2xl p-5">
    <p class="text-xs text-slate-400">{{ label }}</p>
    <p class="mt-2 text-2xl font-bold text-white" :class="tone">{{ value }}</p>
    <p v-if="sub || up !== null" class="mt-2 flex items-center gap-1.5 text-xs">
      <span v-if="up !== null" :class="up ? 'text-emerald-300' : 'text-rose-300'">{{ up ? '↑' : '↓' }}</span>
      <span class="text-slate-500">{{ sub }}</span>
    </p>
  </div>
</template>
