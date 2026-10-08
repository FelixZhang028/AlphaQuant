<template>
  <div class="metrics-panel panel">
    <div class="panel-title">实时性能指标</div>

    <!-- 四个核心指标 -->
    <div class="metric-grid">
      <div class="metric">
        <div class="metric-value">{{ perf.process_rate.toFixed(1) }}</div>
        <div class="metric-label">系统处理速率（笔/秒）</div>
      </div>
      <div class="metric">
        <div class="metric-value">{{ perf.throughput.toFixed(1) }}</div>
        <div class="metric-label">当前吞吐量（笔/秒）</div>
      </div>
      <div class="metric">
        <div class="metric-value" :class="{ warn: perf.avg_latency > 25 }">
          {{ perf.avg_latency.toFixed(2) }}
        </div>
        <div class="metric-label">订单平均处理延迟（ms）</div>
      </div>
      <div class="metric">
        <div class="metric-value">{{ perf.pending_orders_count }}</div>
        <div class="metric-label">当前挂起订单数</div>
      </div>
    </div>

    <!-- 各模块负载条 -->
    <div class="loads">
      <div v-for="m in store.moduleLoad" :key="m.key" class="load-row">
        <span class="load-name">{{ m.name }}</span>
        <div class="load-track">
          <div
            class="load-fill"
            :style="{
              width: m.load + '%',
              background: `linear-gradient(90deg, ${m.color}66, ${m.color})`,
              boxShadow: `0 0 8px ${m.color}88`,
            }"
          ></div>
        </div>
        <span class="load-pct">{{ m.load.toFixed(0) }}%</span>
      </div>
    </div>

    <!-- 动态分析文案 -->
    <div class="analysis">{{ store.analysisLine }}</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useDashboardStore } from '../stores/dashboard'

const store = useDashboardStore()
const perf = computed(() => store.performance)
</script>

<style scoped>
.metrics-panel {
  padding-bottom: 14px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  padding: 0 16px;
}
.metric {
  background: rgba(56, 189, 248, 0.05);
  border: 1px solid rgba(56, 189, 248, 0.1);
  border-radius: 8px;
  padding: 10px 12px;
}
.metric-value {
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--accent-2);
  font-variant-numeric: tabular-nums;
}
.metric-value.warn {
  color: var(--orange);
  text-shadow: 0 0 12px rgba(249, 115, 22, 0.5);
}
.metric-label {
  margin-top: 2px;
  font-size: 0.72rem;
  color: var(--text-dim);
}
.loads {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 0 16px;
}
.load-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.78rem;
}
.load-name {
  width: 64px;
  color: var(--text-dim);
  flex-shrink: 0;
}
.load-track {
  flex: 1;
  height: 8px;
  background: rgba(148, 163, 184, 0.12);
  border-radius: 4px;
  overflow: hidden;
}
.load-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.6s ease;
}
.load-pct {
  width: 40px;
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: var(--text);
  flex-shrink: 0;
}
.analysis {
  margin: 0 16px;
  padding: 10px 12px;
  border-left: 3px solid var(--accent);
  background: rgba(56, 189, 248, 0.06);
  border-radius: 0 8px 8px 0;
  font-size: 0.82rem;
  color: var(--text);
}
</style>
