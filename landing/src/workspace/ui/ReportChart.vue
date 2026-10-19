<script setup>
// 报告里的折线图：纵轴按数据的实际范围（不强行包含 0），可以画几条参考线和日期上的事件标记；
// 鼠标移到图上显示那一天的数值。
import { computed, ref } from 'vue'

const props = defineProps({
  labels: { type: Array, default: () => [] },          // 横轴：日期或报告期
  series: { type: Array, default: () => [] },          // [{ label, color, values: (number|null)[] }]
  bands: { type: Array, default: () => [] },           // 参考线 [{ label, value, color }]
  markers: { type: Array, default: () => [] },         // 事件 [{ index, kind, text }]
  height: { type: Number, default: 200 },
  format: { type: Function, default: (v) => (Number.isFinite(v) ? v.toFixed(2) : '—') },
  zeroLine: { type: Boolean, default: false },
})

const W = 1000
const H = 200
const PAD = 8

const range = computed(() => {
  const values = [...props.series.flatMap((s) => s.values), ...props.bands.map((b) => b.value)].filter((v) => Number.isFinite(v))
  if (props.zeroLine) values.push(0)
  if (!values.length) return null
  let min = Math.min(...values)
  let max = Math.max(...values)
  if (min === max) { min -= 1; max += 1 }
  const pad = (max - min) * 0.06
  return { min: min - pad, max: max + pad }
})
const x = (i) => (props.labels.length <= 1 ? W / 2 : (i / (props.labels.length - 1)) * W)
const y = (v) => PAD + (1 - (v - range.value.min) / (range.value.max - range.value.min)) * (H - PAD * 2)

const paths = computed(() => {
  if (!range.value) return []
  return props.series.map((s) => {
    let d = ''
    let open = false
    s.values.forEach((v, i) => {
      if (!Number.isFinite(v)) { open = false; return }
      d += `${open ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)} `
      open = true
    })
    return { ...s, d: d.trim() }
  })
})
const lines = computed(() => (range.value ? props.bands.filter((b) => Number.isFinite(b.value)).map((b) => ({ ...b, top: (y(b.value) / H) * 100 })) : []))
const zero = computed(() => (range.value && props.zeroLine ? (y(0) / H) * 100 : null))
const ticks = computed(() => {
  const n = props.labels.length
  if (!n) return []
  const picks = n > 2 ? [0, Math.floor((n - 1) / 2), n - 1] : [...Array(n).keys()]
  return picks.map((i) => ({ text: props.labels[i], left: (x(i) / W) * 100 }))
})
const KIND_COLORS = { action: '#34d399', report: '#a5b4fc', index: '#fbbf24', industry: '#f472b6', st: '#f87171' }
const marks = computed(() => props.markers.map((m) => ({ ...m, left: (x(m.index) / W) * 100, color: KIND_COLORS[m.kind] || '#94a3b8' })))

const hover = ref(null)
function onMove(event) {
  const box = event.currentTarget.getBoundingClientRect()
  const n = props.labels.length
  if (!n || !box.width) return
  const i = Math.max(0, Math.min(n - 1, Math.round(((event.clientX - box.left) / box.width) * (n - 1))))
  hover.value = {
    index: i, left: (x(i) / W) * 100, label: props.labels[i],
    values: props.series.map((s) => ({ label: s.label, color: s.color, text: props.format(s.values[i]) })),
    events: props.markers.filter((m) => m.index === i).map((m) => m.text),
  }
}
</script>

<template>
  <div v-if="range" class="select-none">
    <div class="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
      <span v-for="s in series" :key="s.label" class="flex items-center gap-1.5"><span class="h-0.5 w-4 rounded" :style="{ background: s.color }" />{{ s.label }}</span>
      <span v-for="b in lines" :key="b.label" class="flex items-center gap-1.5"><span class="h-0 w-4 border-t border-dashed" :style="{ borderColor: b.color }" />{{ b.label }} {{ format(b.value) }}</span>
    </div>
    <div class="relative" :style="{ height: `${height}px` }" @mousemove="onMove" @mouseleave="hover = null">
      <svg :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="none" class="absolute inset-0 h-full w-full" aria-hidden="true">
        <path v-for="p in paths" :key="p.label" :d="p.d" fill="none" :stroke="p.color" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round" />
      </svg>
      <div v-for="b in lines" :key="b.label" class="pointer-events-none absolute inset-x-0 border-t border-dashed opacity-60" :style="{ top: `${b.top}%`, borderColor: b.color }" />
      <div v-if="zero !== null" class="pointer-events-none absolute inset-x-0 border-t border-white/20" :style="{ top: `${zero}%` }" />
      <span v-for="(m, i) in marks" :key="i" class="pointer-events-none absolute bottom-0 h-2 w-2 -translate-x-1/2 rounded-full ring-2 ring-ink" :style="{ left: `${m.left}%`, background: m.color }" />
      <span class="pointer-events-none absolute left-0 top-0 text-[10px] text-slate-500">{{ format(range.max) }}</span>
      <span class="pointer-events-none absolute bottom-3 left-0 text-[10px] text-slate-500">{{ format(range.min) }}</span>
      <template v-if="hover">
        <div class="pointer-events-none absolute inset-y-0 w-px bg-white/30" :style="{ left: `${hover.left}%` }" />
        <div class="pointer-events-none absolute top-1 z-10 min-w-[9rem] rounded-lg border border-white/15 bg-ink/95 px-3 py-2 text-xs shadow-lg"
          :style="hover.left > 60 ? { right: `${100 - hover.left + 1}%` } : { left: `${hover.left + 1}%` }">
          <p class="text-slate-300">{{ hover.label }}</p>
          <p v-for="v in hover.values" :key="v.label" class="mt-0.5 flex justify-between gap-3"><span :style="{ color: v.color }">{{ v.label }}</span><span class="text-white">{{ v.text }}</span></p>
          <p v-for="text in hover.events" :key="text" class="mt-1 text-amber-200">{{ text }}</p>
        </div>
      </template>
    </div>
    <div class="relative mt-1 h-4 text-[10px] text-slate-500">
      <span v-for="(t, i) in ticks" :key="i" class="absolute whitespace-nowrap" :class="i === 0 ? '' : i === ticks.length - 1 ? '-translate-x-full' : '-translate-x-1/2'" :style="{ left: `${t.left}%` }">{{ t.text }}</span>
    </div>
  </div>
  <div v-else class="flex items-center justify-center rounded-xl border border-dashed border-white/10 text-sm text-slate-500" :style="{ height: `${height}px` }">暂无数据</div>
</template>
