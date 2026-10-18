<template>
  <div class="stat-card panel">
    <div class="stat-value">
      {{ displayValue }}<span v-if="suffix" class="stat-suffix">{{ suffix }}</span>
    </div>
    <div class="stat-label">{{ label }}</div>
  </div>
</template>

<script setup>
import { ref, watch, onUnmounted } from 'vue'

const props = defineProps({
  label: { type: String, required: true },
  value: { type: Number, default: 0 },
  suffix: { type: String, default: '' },
})

// 数字变化时做 600ms 的 count-up 动画
const displayValue = ref(0)
let rafId = null

function animateTo(target) {
  if (rafId) cancelAnimationFrame(rafId)
  const from = Number(displayValue.value) || 0
  const start = performance.now()
  const duration = 600
  const tick = (now) => {
    const t = Math.min(1, (now - start) / duration)
    const eased = 1 - Math.pow(1 - t, 3) // easeOutCubic
    displayValue.value = Math.round(from + (target - from) * eased)
    if (t < 1) rafId = requestAnimationFrame(tick)
  }
  rafId = requestAnimationFrame(tick)
}

watch(() => props.value, (v) => animateTo(v), { immediate: true })
onUnmounted(() => rafId && cancelAnimationFrame(rafId))
</script>

<style scoped>
.stat-card {
  flex: 1;
  min-width: 140px;
  padding: 16px 18px;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 0 32px rgba(56, 189, 248, 0.12);
}
.stat-value {
  font-size: 2rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--accent);
  text-shadow: 0 0 16px rgba(56, 189, 248, 0.45);
}
.stat-suffix {
  font-size: 0.85rem;
  color: var(--text-dim);
  margin-left: 4px;
  text-shadow: none;
}
.stat-label {
  margin-top: 4px;
  font-size: 0.8rem;
  color: var(--text-dim);
  letter-spacing: 0.08em;
}
</style>
