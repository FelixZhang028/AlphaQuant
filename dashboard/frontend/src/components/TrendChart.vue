<template>
  <div class="trend-panel panel">
    <div class="panel-title">吞吐 / 延迟 · 近 1 分钟</div>
    <div ref="chartEl" class="trend-chart"></div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { useDashboardStore } from '../stores/dashboard'

const store = useDashboardStore()
const chartEl = ref(null)
let chart = null

function buildOption() {
  const history = store.history
  const times = history.map((p) =>
    new Date(p.ts * 1000).toLocaleTimeString('zh-CN', { hour12: false })
  )
  return {
    animationDurationUpdate: 300,
    grid: { left: 52, right: 48, top: 34, bottom: 26 },
    legend: {
      data: ['吞吐量', '平均延迟'],
      textStyle: { color: '#7d93b2', fontSize: 11 },
      top: 4,
      icon: 'roundRect',
      itemWidth: 12,
      itemHeight: 3,
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(8,18,36,0.95)',
      borderColor: 'rgba(56,189,248,0.3)',
      textStyle: { color: '#dbe7f5', fontSize: 12 },
    },
    xAxis: {
      type: 'category',
      data: times,
      boundaryGap: false,
      axisLine: { lineStyle: { color: 'rgba(56,189,248,0.2)' } },
      axisLabel: { color: '#7d93b2', fontSize: 10, interval: 14 },
    },
    yAxis: [
      {
        type: 'value',
        name: '笔/秒',
        nameTextStyle: { color: '#7d93b2', fontSize: 10 },
        splitLine: { lineStyle: { color: 'rgba(56,189,248,0.08)' } },
        axisLabel: { color: '#7d93b2', fontSize: 10 },
      },
      {
        type: 'value',
        name: 'ms',
        nameTextStyle: { color: '#7d93b2', fontSize: 10 },
        splitLine: { show: false },
        axisLabel: { color: '#7d93b2', fontSize: 10 },
      },
    ],
    series: [
      {
        name: '吞吐量',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: history.map((p) => p.throughput),
        lineStyle: { color: '#38bdf8', width: 2, shadowColor: '#38bdf8', shadowBlur: 10 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(56,189,248,0.28)' },
            { offset: 1, color: 'rgba(56,189,248,0)' },
          ]),
        },
      },
      {
        name: '平均延迟',
        type: 'line',
        smooth: true,
        showSymbol: false,
        yAxisIndex: 1,
        data: history.map((p) => p.latency),
        lineStyle: { color: '#f97316', width: 1.6, type: 'dashed' },
      },
    ],
  }
}

onMounted(() => {
  chart = echarts.init(chartEl.value)
  chart.setOption(buildOption())
  window.addEventListener('resize', handleResize)
})

function handleResize() {
  chart?.resize()
}

watch(
  () => store.history,
  () => {
    if (chart && !store.paused) chart.setOption(buildOption())
  },
  { deep: true }
)

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.trend-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.trend-chart {
  flex: 1;
  min-height: 220px;
}
</style>
