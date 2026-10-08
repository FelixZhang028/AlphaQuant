<template>
  <transition name="slide">
    <div v-if="module" class="node-detail panel" :style="{ '--mc': module.color }">
      <div class="detail-header">
        <span class="detail-dot"></span>
        <span class="detail-name">{{ module.name }}</span>
        <button class="close-btn" @click="store.selectModule(module.key)">×</button>
      </div>
      <p class="detail-desc">{{ module.desc }}</p>
      <div class="detail-row">
        <span>实时负载</span>
        <span class="mono">{{ store.loadOf(module.key).toFixed(1) }}%</span>
      </div>
      <div class="detail-track">
        <div
          class="detail-fill"
          :style="{ width: store.loadOf(module.key) + '%', background: module.color }"
        ></div>
      </div>
      <div class="detail-row">
        <span>状态</span>
        <span :style="{ color: statusColor }">{{ statusText }}</span>
      </div>
      <p class="detail-hint">长按图中节点可打断当前任务并由指令环重派</p>
    </div>
  </transition>
</template>

<script setup>
import { computed } from 'vue'
import { useDashboardStore, MODULES } from '../stores/dashboard'

const store = useDashboardStore()
const module = computed(() => MODULES.find((m) => m.key === store.selectedModule) || null)

const load = computed(() => (module.value ? store.loadOf(module.value.key) : 0))
const statusText = computed(() =>
  load.value >= 90 ? '过载' : load.value >= 70 ? '繁忙' : '正常'
)
const statusColor = computed(() =>
  load.value >= 90 ? 'var(--red)' : load.value >= 70 ? 'var(--orange)' : 'var(--green)'
)
</script>

<style scoped>
.node-detail {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 250px;
  padding: 14px 16px;
  z-index: 10;
  border-color: color-mix(in srgb, var(--mc) 45%, transparent);
  box-shadow: 0 0 28px color-mix(in srgb, var(--mc) 25%, transparent);
}
.detail-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.detail-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--mc);
  box-shadow: 0 0 10px var(--mc);
}
.detail-name {
  font-weight: 600;
  color: var(--mc);
  flex: 1;
}
.close-btn {
  background: none;
  border: none;
  color: var(--text-dim);
  font-size: 1.1rem;
  cursor: pointer;
  line-height: 1;
}
.close-btn:hover {
  color: var(--text);
}
.detail-desc {
  font-size: 0.78rem;
  color: var(--text-dim);
  margin-bottom: 12px;
  line-height: 1.5;
}
.detail-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.8rem;
  margin-bottom: 6px;
}
.mono {
  font-variant-numeric: tabular-nums;
}
.detail-track {
  height: 6px;
  border-radius: 3px;
  background: rgba(148, 163, 184, 0.12);
  overflow: hidden;
  margin-bottom: 10px;
}
.detail-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.5s ease;
}
.detail-hint {
  margin-top: 10px;
  font-size: 0.68rem;
  color: var(--text-dim);
  opacity: 0.7;
}
.slide-enter-active,
.slide-leave-active {
  transition: all 0.25s ease;
}
.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  transform: translateX(16px);
}
</style>
