<template>
  <div class="dashboard">
    <!-- header：标题 + 连接状态 -->
    <header class="top-bar">
      <div class="brand">
        <span class="brand-dot"></span>
        <h1 class="brand-title">智投引擎 · 实时监控</h1>
      </div>
      <ConnectionBadge />
    </header>

    <!-- stats-row：顶部 5 个统计卡 -->
    <section class="stats-row">
      <StatCard label="活跃策略" :value="store.overview.active_strategies" />
      <StatCard label="执行中" :value="store.overview.running_instances" />
      <StatCard label="数据链路" :value="store.overview.data_links" />
      <StatCard label="待处理指令" :value="store.overview.pending_orders" />
      <StatCard label="今日成交" :value="store.overview.today_trades" />
    </section>

    <!-- mesh-section：Mesh 网络图居中 + NodeDetail 覆层 -->
    <section class="mesh-section">
      <MeshGraph class="mesh-graph" />
      <NodeDetail />
    </section>

    <!-- bottom-row：性能面板 + 趋势图 -->
    <section class="bottom-row">
      <MetricsPanel class="metrics-box" />
      <TrendChart class="trend-box" />
    </section>

    <!-- HintBar：底部操作提示 -->
    <HintBar />
  </div>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useDashboardStore } from './stores/dashboard'
import { dashboardService } from './services/dashboardService'
import ConnectionBadge from './components/ConnectionBadge.vue'
import StatCard from './components/StatCard.vue'
import MeshGraph from './components/MeshGraph.vue'
import NodeDetail from './components/NodeDetail.vue'
import MetricsPanel from './components/MetricsPanel.vue'
import TrendChart from './components/TrendChart.vue'
import HintBar from './components/HintBar.vue'

const store = useDashboardStore()

// 空格键：暂停 / 恢复实时更新
function onKeydown(e) {
  if (e.code === 'Space' && !e.repeat) {
    const tag = document.activeElement?.tagName
    if (tag !== 'INPUT' && tag !== 'TEXTAREA' && tag !== 'BUTTON') {
      e.preventDefault()
      store.togglePaused()
    }
  }
}

onMounted(() => {
  dashboardService.start()
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  dashboardService.stop()
  window.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
.dashboard {
  height: 100vh;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px 18px 12px;
}
.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}
.brand-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 16px var(--accent);
}
.brand-title {
  font-size: 1.2rem;
  font-weight: 700;
  letter-spacing: 0.03em;
  color: var(--text);
}
.stats-row {
  display: flex;
  gap: 12px;
}
.mesh-section {
  flex: 1;
  position: relative;
  min-height: 300px;
}
.mesh-graph {
  position: absolute;
  inset: 0;
}
.bottom-row {
  display: flex;
  gap: 14px;
  height: 250px;
  flex: none;
}
.metrics-box {
  width: 430px;
  flex: none;
  height: 100%;
}
.trend-box {
  flex: 1;
  min-width: 0;
  height: 100%;
}
</style>
