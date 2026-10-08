<script setup>
import { computed } from 'vue'

const props = defineProps({
  series: { type: Array, default: () => [] }, // array of { label, color, points: number[] }
  height: { type: Number, default: 160 },
  fill: { type: Boolean, default: true },
})

const W = 100
const H = 40

const paths = computed(() => {
  if (!props.series.length) return []
  const all = props.series.flatMap((s) => s.points)
  const max = Math.max(...all, 0)
  const min = Math.min(...all, 0)
  const span = max - min || 1
  return props.series.map((s) => {
    const step = W / Math.max(s.points.length - 1, 1)
    const d = s.points
      .map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${(H - ((v - min) / span) * H).toFixed(1)}`)
      .join(' ')
    return { ...s, d, area: `${d} L${W},${H} L0,${H} Z` }
  })
})
</script>

<template>
  <svg v-if="paths.length" viewBox="0 0 100 40" class="w-full" :style="{ height: height + 'px' }" preserveAspectRatio="none">
    <defs>
      <linearGradient v-for="(p, i) in paths" :id="`lc-${i}`" :key="i" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" :stop-color="p.color" stop-opacity="0.3" />
        <stop offset="100%" :stop-color="p.color" stop-opacity="0" />
      </linearGradient>
    </defs>
    <template v-for="(p, i) in paths" :key="i">
      <path v-if="fill" :d="p.area" :fill="`url(#lc-${i})`" />
      <path :d="p.d" fill="none" :stroke="p.color" stroke-width="0.7" stroke-linecap="round" stroke-linejoin="round" />
    </template>
  </svg>
  <div v-else class="flex items-center justify-center rounded-xl border border-dashed border-white/10 p-8 text-sm text-slate-500" :style="{ height: height + 'px' }">暂无数据</div>
</template>
