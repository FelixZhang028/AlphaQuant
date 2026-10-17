<template>
  <div class="mesh-graph">
    <!-- ECharts 渲染：graph 节点/连线 + lines 流动粒子 -->
    <div ref="chartEl" class="mesh-chart"></div>

    <!-- 长按打断重派提示（顶部） -->
    <transition name="fade">
      <div v-if="toast" class="mesh-toast">{{ toast }}</div>
    </transition>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { useDashboardStore, MODULES } from '../stores/dashboard'

const store = useDashboardStore()
const chartEl = ref(null)
const toast = ref('')

// 模块间数据/指令流向（连线 + 粒子按此绘制）
const EDGES = [
  ['market', 'data'],
  ['data', 'strategy'],
  ['strategy', 'risk'],
  ['risk', 'execution'],
  ['execution', 'order'],
  ['order', 'strategy'],
  ['data', 'risk'],
  ['execution', 'market'],
]

const RING_RADIUS = 150 // 圆环布局半径
const LONG_PRESS_MS = 600

let chart = null
let W = 0
let H = 0
let nodesData = [] // 当前节点数据（供 hit 检测与粒子坐标）
let pulseTimer = null
let pulsePhase = 0
let pressTimer = null
let pressKey = null
let longPressed = false
let lastLongPressAt = 0
let toastTimer = null

/** 节点在圆环上的像素坐标（相对容器） */
function ringXY(i, total) {
  const angle = (Math.PI * 2 * i) / total - Math.PI / 2
  return [W / 2 + RING_RADIUS * Math.cos(angle), H / 2 + RING_RADIUS * Math.sin(angle)]
}

/** 组装 graph 节点：大小随负载变化、带模块色发光 */
function buildNodes() {
  return MODULES.map((m, i) => {
    const [x, y] = ringXY(i, MODULES.length)
    const load = store.loadOf(m.key)
    return {
      id: m.key,
      name: m.name,
      x,
      y,
      symbolSize: 56 + load * 0.9,
      itemStyle: {
        color: m.color,
        borderColor: 'rgba(255,255,255,0.28)',
        borderWidth: 1.2,
        shadowColor: m.color,
        shadowBlur: 22,
      },
      label: {
        show: true,
        formatter: m.name,
        position: 'bottom',
        distance: 12,
        color: '#dbe7f5',
        fontSize: 13,
        fontWeight: 600,
        textShadowColor: 'rgba(56,189,248,0.55)',
        textShadowBlur: 10,
      },
      // 额外挂载字段（tooltip / 交互用）
      _key: m.key,
      _desc: m.desc,
      _load: load,
      _color: m.color,
    }
  })
}

function buildEdges() {
  return EDGES.map(([s, t]) => ({
    source: s,
    target: t,
    lineStyle: {
      color: 'rgba(56,189,248,0.35)',
      width: 1.4,
      curveness: 0.2,
      shadowColor: 'rgba(56,189,248,0.45)',
      shadowBlur: 6,
    },
  }))
}

function buildLines() {
  return EDGES.map(([s, t]) => {
    const si = MODULES.findIndex((m) => m.key === s)
    const ti = MODULES.findIndex((m) => m.key === t)
    const [x1, y1] = ringXY(si, MODULES.length)
    const [x2, y2] = ringXY(ti, MODULES.length)
    return { coords: [[x1, y1], [x2, y2]] }
  })
}

/** 粒子周期：随实时吞吐变化（吞吐越大 period 越小，流速越快） */
function flowPeriod() {
  const tp = store.performance.throughput || 0
  return Math.max(1, 6 - tp / 15)
}

function baseOption() {
  return {
    backgroundColor: 'transparent',
    animationDurationUpdate: 300,
    tooltip: {
      trigger: 'item',
      confine: true,
      backgroundColor: 'rgba(8,18,36,0.95)',
      borderColor: 'rgba(56,189,248,0.4)',
      borderWidth: 1,
      padding: 10,
      textStyle: { color: '#dbe7f5', fontSize: 12 },
      formatter: (p) => {
        if (p.dataType !== 'node') return ''
        const d = p.data
        const load = store.loadOf(d._key)
        const status = load >= 90 ? '过载' : load >= 70 ? '繁忙' : '正常'
        const color = load >= 90 ? '#ef4444' : load >= 70 ? '#f97316' : '#22c55e'
        return (
          `<div style="font-weight:700;color:${d._color}">${d.name}</div>` +
          `<div style="color:#7d93b2;margin-top:2px;max-width:220px">${d._desc}</div>` +
          `<div style="margin-top:6px;font-variant-numeric:tabular-nums">` +
          `实时负载 <b style="color:${color}">${load.toFixed(1)}%</b>（${status}）</div>`
        )
      },
    },
    // 隐藏坐标轴：仅为 lines(cartesian2d) 提供与像素一致的坐标域
    xAxis: { type: 'value', min: 0, max: W, show: false },
    yAxis: { type: 'value', min: 0, max: H, show: false },
    series: [
      {
        type: 'graph',
        layout: 'none',
        data: buildNodes(),
        edges: buildEdges(),
        roam: false,
        draggable: false,
        z: 3,
        lineStyle: { curveness: 0.2 },
        emphasis: {
          focus: 'adjacency',
          itemStyle: { shadowBlur: 38 },
          lineStyle: { width: 2.6, opacity: 0.95 },
        },
      },
      {
        type: 'lines',
        coordinateSystem: 'cartesian2d',
        zlevel: 4,
        effect: {
          show: !store.paused,
          period: flowPeriod(),
          trailLength: 0.35,
          symbol: 'circle',
          symbolSize: 5,
          color: '#7dd3fc',
          loop: true,
        },
        lineStyle: { width: 1, color: 'rgba(56,189,248,0.4)', curveness: 0.2, opacity: 0 },
        data: buildLines(),
      },
    ],
  }
}

/* ------------------------------------------------------------------ */
/* 交互：悬停(tooltip 内置) / 单击(selectModule) / 长按(打断重派)       */
/* ------------------------------------------------------------------ */

/** 像素坐标命中检测（节点为像素布局，直接距离判断） */
function hitNode(px, py) {
  for (const n of nodesData) {
    const r = n.symbolSize / 2 + 8
    const dx = px - n.x
    const dy = py - n.y
    if (dx * dx + dy * dy <= r * r) return n
  }
  return null
}

function onMouseDown(e) {
  const rect = chartEl.value.getBoundingClientRect()
  const node = hitNode(e.clientX - rect.left, e.clientY - rect.top)
  if (!node) return
  pressKey = node._key
  longPressed = false
  pressTimer = setTimeout(() => {
    longPressed = true
    lastLongPressAt = Date.now()
    const name = MODULES.find((m) => m.key === pressKey)?.name || pressKey
    showToast(`已打断「${name}」当前任务，指令环已重派`)
    pressKey = null
  }, LONG_PRESS_MS)
}

function onMouseUp() {
  if (pressTimer) clearTimeout(pressTimer)
  pressTimer = null
  longPressed = false
  pressKey = null
}

function onClick(params) {
  // 刚发生过长按（松手会附带一次 click），抑制，避免误开详情
  if (Date.now() - lastLongPressAt < 350) return
  if (params.dataType === 'node' && params.data && params.data._key) {
    store.selectModule(params.data._key)
  }
}

function showToast(msg) {
  toast.value = msg
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (toast.value = ''), 2200)
}

/* ------------------------------------------------------------------ */
/* 动画驱动：呼吸脉冲 + 节点大小 + 粒子流速                            */
/* ------------------------------------------------------------------ */
function pulseTick() {
  if (store.paused) return // 暂停时停止动画
  pulsePhase += 0.06
  nodesData = buildNodes()
  nodesData.forEach((n) => {
    const ph = pulsePhase + n._key.length * 1.37
    const breathe = 0.88 + 0.12 * Math.sin(ph)
    n.symbolSize = Math.max(20, n.symbolSize * breathe)
    n.itemStyle.shadowBlur =
      16 + 12 * (0.5 + 0.5 * Math.sin(ph)) + (n._load / 100) * 12
  })
  chart.setOption({
    series: [
      { data: nodesData },
      { effect: { period: flowPeriod() } },
    ],
  })
}

/* ------------------------------------------------------------------ */
/* 生命周期                                                             */
/* ------------------------------------------------------------------ */
function onResize() {
  if (!chart) return
  W = chartEl.value.clientWidth
  H = chartEl.value.clientHeight
  chart.resize()
  nodesData = buildNodes()
  chart.setOption(baseOption(), { notMerge: true })
}

// 暂停时隐藏粒子、恢复时重新显示
watch(
  () => store.paused,
  (paused) => {
    chart?.setOption({ series: [{}, { effect: { show: !paused } }] })
  }
)

onMounted(() => {
  W = chartEl.value.clientWidth
  H = chartEl.value.clientHeight
  chart = echarts.init(chartEl.value)
  nodesData = buildNodes()
  chart.setOption(baseOption())
  chart.on('click', onClick)
  chartEl.value.addEventListener('mousedown', onMouseDown)
  window.addEventListener('mouseup', onMouseUp)
  window.addEventListener('resize', onResize)
  pulseTimer = setInterval(pulseTick, 250)
})

onUnmounted(() => {
  if (pulseTimer) clearInterval(pulseTimer)
  if (pressTimer) clearTimeout(pressTimer)
  if (toastTimer) clearTimeout(toastTimer)
  chartEl.value?.removeEventListener('mousedown', onMouseDown)
  window.removeEventListener('mouseup', onMouseUp)
  window.removeEventListener('resize', onResize)
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.mesh-graph {
  width: 100%;
  height: 100%;
  position: relative;
}
.mesh-chart {
  width: 100%;
  height: 100%;
}
.mesh-toast {
  position: absolute;
  top: 14px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 20;
  padding: 8px 18px;
  border-radius: 8px;
  background: rgba(8, 18, 36, 0.92);
  border: 1px solid rgba(249, 115, 22, 0.55);
  color: #fb923c;
  font-size: 0.8rem;
  box-shadow: 0 0 24px rgba(249, 115, 22, 0.25);
  pointer-events: none;
  white-space: nowrap;
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
