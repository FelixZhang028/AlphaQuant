<template>
  <div class="hint-bar">
    <span v-for="(h, i) in hints" :key="i" class="hint">
      <kbd>{{ h.key }}</kbd>{{ h.text }}
      <span v-if="i < hints.length - 1" class="sep">·</span>
    </span>
    <span v-if="store.paused" class="paused-tag">已暂停更新</span>
  </div>
</template>

<script setup>
import { useDashboardStore } from '../stores/dashboard'

const store = useDashboardStore()
const hints = [
  { key: '光标', text: '靠近 = 指令环把它们唤过来' },
  { key: '单击', text: '查看节点详情' },
  { key: '长按', text: '打断并重派' },
  { key: '空格', text: '暂停 / 恢复' },
]
</script>

<style scoped>
.hint-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 6px 14px;
  padding: 10px 16px;
  font-size: 0.75rem;
  color: var(--text-dim);
}
kbd {
  display: inline-block;
  padding: 1px 7px;
  margin-right: 5px;
  border: 1px solid var(--border);
  border-bottom-width: 2px;
  border-radius: 5px;
  background: rgba(56, 189, 248, 0.07);
  color: var(--accent);
  font-family: inherit;
  font-size: 0.72rem;
}
.sep {
  margin-left: 14px;
  opacity: 0.4;
}
.paused-tag {
  margin-left: 14px;
  padding: 2px 10px;
  border-radius: 999px;
  border: 1px solid rgba(249, 115, 22, 0.5);
  color: var(--orange);
  animation: blink 1.2s infinite;
}
@keyframes blink {
  50% { opacity: 0.4; }
}
</style>
