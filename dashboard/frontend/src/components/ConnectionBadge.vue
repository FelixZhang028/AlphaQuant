<template>
  <div class="conn-badge" :class="status">
    <span class="dot"></span>
    <span class="text">{{ text }}</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useDashboardStore } from '../stores/dashboard'

const store = useDashboardStore()
const status = computed(() => store.connection)
const text = computed(
  () =>
    ({
      realtime: '实时',
      polling: '轮询',
      disconnected: '断开',
    }[store.connection] || '断开')
)
</script>

<style scoped>
.conn-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 999px;
  font-size: 0.78rem;
  letter-spacing: 0.1em;
  border: 1px solid var(--border);
  background: var(--bg-panel);
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #94a3b8;
}
.realtime .dot {
  background: var(--green);
  box-shadow: 0 0 10px var(--green);
  animation: blink 1.4s infinite;
}
.polling .dot {
  background: var(--orange);
  box-shadow: 0 0 10px var(--orange);
}
.disconnected .dot {
  background: var(--red);
  box-shadow: 0 0 10px var(--red);
}
.realtime .text { color: var(--green); }
.polling .text { color: var(--orange); }
.disconnected .text { color: var(--red); }
@keyframes blink {
  50% { opacity: 0.35; }
}
</style>
