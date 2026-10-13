<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { dispose, init } from 'klinecharts'
import { chartDrawings, localMarketBars, saveChartDrawings } from '../../api.js'
import { useTheme } from '../../theme.js'
import { aggregateBars, barsInRange, formatVolume, toCandles, tradeMarks } from '../klinePresentation.js'
import { DRAWING_TOOLS, MAX_DRAWINGS, drawingOverlays, storedDrawings } from '../klineDrawings.js'
import { TRADE_COLORS } from '../klineOverlays.js'

const props = defineProps({
  symbol: { type: String, required: true },
  // 一次回测在这只股票上的记录：{ fills, rejected, holdings }；为 null 时不画。
  trades: { type: Object, default: null },
})
// 每次读取结束后通知父组件：成功时为接口返回的日线数据，失败或无数据时为 null。
const emit = defineEmits(['loaded'])

const PERIODS = [{ key: 'day', label: '日K' }, { key: 'week', label: '周K' }, { key: 'month', label: '月K' }]
const RANGES = [{ key: '3m', label: '近3月' }, { key: '1y', label: '近1年' }, { key: '3y', label: '近3年' }, { key: 'all', label: '全部' }]
const DEFAULT_RANGE = { day: '1y', week: '3y', month: 'all' }
const SUBS = [{ key: 'MACD', label: 'MACD', precision: 3 }, { key: 'KDJ', label: 'KDJ', precision: 2 }, { key: 'RSI', label: 'RSI', precision: 2 }, { key: 'none', label: '无' }]
const ADJUSTS = [{ key: 'forward', label: '前复权' }, { key: 'none', label: '不复权' }]
const SUB_PANE = 'sub_pane'
const TRADE_GROUP = 'backtest_trades'
const DRAW_GROUP = 'user_drawings'
const SAVE_DELAY = 400
const LEGEND = [
  { label: '买入', color: TRADE_COLORS.buy }, { label: '卖出', color: TRADE_COLORS.sell },
  { label: '未成交订单', color: TRADE_COLORS.reject }, { label: '收盘时持有', color: TRADE_COLORS.holding, wide: true },
]
// A 股习惯：红涨绿跌。
const RISE = '#ef4444'
const FALL = '#22c55e'
const FLAT = '#94a3b8'
const MIN_BAR_SPACE = 0.3
const MAX_BAR_SPACE = 50
// 窄屏放不下常驻的数值栏：改为触摸或悬停时再显示。
const COMPACT_WIDTH = 480

const { theme } = useTheme()
const container = ref(null)
const period = ref('day')
const range = ref('1y')
const sub = ref('MACD')
const adjust = ref('forward')
const loading = ref(false)
const error = ref('')
const missing = ref(false)
const result = ref(null)
// 当前图上回测标记的数量：{ shown, missing }；没有叠加回测时为 null。
const marked = ref(null)
// ---------- 画线 ----------
// 正在使用的画线工具（画完或取消后为空）、选中的线、已画的数量、提示或错误。
const tool = ref('')
const selected = ref('')
const drawingCount = ref(0)
const drawingNote = ref('')
const drawingsReady = ref(false)
const confirmingClear = ref(false)
// drawings 是保存用的形式（日期 + 不复权价格），图上的线每次由它重画。
let drawings = []
let pendingId = null
let redrawing = false
let drawingsRequest = 0
let unsaved = null
let saveTimer = null
let chart = null
let shown = []
let request = 0
let observer = null
let width = 0

const message = computed(() => {
  if (loading.value) return '正在读取K线…'
  if (error.value) return error.value
  if (missing.value) return '尚未下载行情，更新行情后可查看K线。'
  if (result.value && !result.value.bars.length) return '本地行情缺少完整的开高低收价格，无法绘制K线。'
  return ''
})
const caption = computed(() => {
  const data = result.value
  if (!data?.bars.length) return ''
  const parts = [`${data.adjust === 'forward' ? '前复权' : '不复权'} · ${data.start_date} 至 ${data.end_date} · 共 ${data.bars.length} 个交易日 · 成交量单位：股`]
  if (adjust.value === 'forward' && data.adjust !== 'forward') parts.push('该股票缺少复权因子，当前显示不复权价格')
  if (data.suspended_days) parts.push(`停牌 ${data.suspended_days} 天未显示`)
  if (data.invalid_rows) parts.push(`${data.invalid_rows} 条记录价格不完整未显示`)
  return parts.join('；')
})

function chartStyles() {
  const change = { upColor: RISE, downColor: FALL, noChangeColor: FLAT }
  const compact = width > 0 && width < COMPACT_WIDTH
  const showRule = compact ? 'follow_cross' : 'always'
  return {
    candle: {
      bar: {
        ...change,
        upBorderColor: RISE, downBorderColor: FALL, noChangeBorderColor: FLAT,
        upWickColor: RISE, downWickColor: FALL, noChangeWickColor: FLAT,
      },
      priceMark: { last: change },
      tooltip: {
        showRule,
        showType: compact ? 'rect' : 'standard',
        title: { show: false },
        legend: {
          template: [
            { title: 'time', value: '{time}' }, { title: 'open', value: '{open}' },
            { title: 'high', value: '{high}' }, { title: 'low', value: '{low}' },
            { title: 'close', value: '{close}' }, { title: 'change', value: '{change}' },
            { title: 'volume', value: '{volume}' },
          ],
        },
      },
    },
    indicator: { ohlc: change, bars: [change], tooltip: { showRule } },
  }
}

const controls = computed(() => [
  { label: 'K线周期', items: PERIODS, active: period.value, select: setPeriod },
  { label: 'K线时间范围', items: RANGES, active: range.value, select: setRange },
  { label: '副图指标', items: SUBS, active: sub.value, select: setSub },
  { label: '复权方式', items: ADJUSTS, active: adjust.value, select: setAdjust, busy: loading.value },
])

function applyTheme() {
  chart?.setStyles(theme.value)
  chart?.setStyles(chartStyles())
}

async function applyRange() {
  // 图表在微任务里完成布局；等它结束，才能按新的宽度计算每根 K 线占多宽。
  await Promise.resolve()
  if (!chart || !shown.length) return
  const space = (chart.getSize('candle_pane', 'main')?.width ?? 0) - chart.getOffsetRightDistance()
  if (space <= 0) return
  chart.setBarSpace(Math.min(MAX_BAR_SPACE, Math.max(MIN_BAR_SPACE, space / barsInRange(shown, range.value))))
  chart.scrollToRealTime()
}

// 按当前周期重新合并 K 线并交给图表；setPeriod 会让图表重新向 getBars 取数。
function draw() {
  shown = aggregateBars(result.value?.bars ?? [], period.value)
  chart?.setPeriod({ type: period.value, span: 1 })
  drawTrades()
  renderDrawings()
  applyRange()
}

const timestamp = (date) => new Date(`${date}T00:00:00`).getTime()

// 复权方式或周期变化后，标记的价格和所在的 K 线都会变，所以每次整组重画。
function drawTrades() {
  if (!chart) return
  chart.removeOverlay({ groupId: TRADE_GROUP })
  marked.value = null
  if (!props.trades || !shown.length) return
  const { marks, spans, missing } = tradeMarks(result.value.bars, shown, props.trades)
  chart.createOverlay([
    ...spans.map((span) => ({
      name: 'fqHoldingSpan', groupId: TRADE_GROUP, lock: true, zLevel: -1,
      points: [{ timestamp: timestamp(span.start) }, { timestamp: timestamp(span.end) }],
    })),
    ...marks.map((mark) => ({
      name: 'fqTradeMark', groupId: TRADE_GROUP, lock: true, extendData: mark,
      points: [{ timestamp: timestamp(mark.date), value: mark.value ?? mark.anchor }, { timestamp: timestamp(mark.date), value: mark.anchor }],
    })),
  ])
  marked.value = { shown: marks.length, missing }
}

// 行情还在读取时，图上还是上一只股票或上一种复权方式的 K 线，这时不能画。
const canDraw = computed(() => drawingsReady.value && !loading.value && !!result.value?.bars.length)
const drawingHint = computed(() => {
  if (drawingNote.value) return drawingNote.value
  const active = DRAWING_TOOLS.find((item) => item.name === tool.value)
  if (active) return `${active.hint}再点一次「${active.label}」取消。`
  if (selected.value) return '拖动可以移动这条线，也可以删除它。'
  return drawingCount.value ? `已画 ${drawingCount.value} 条，自动保存。点一条线选中后可以拖动或删除。` : ''
})

// 画线的事件回调。图表在把线真正移除之前调用 onRemoved，所以要把它从结果里排除。
const drawingEvents = {
  onDrawEnd: () => { pendingId = null; tool.value = ''; commitDrawings() },
  onPressedMoveEnd: () => commitDrawings(),
  onRemoved: ({ overlay }) => {
    if (redrawing) return
    if (overlay.id === selected.value) selected.value = ''
    if (overlay.id === pendingId) { pendingId = null; tool.value = ''; return }
    commitDrawings(overlay.id)
  },
  onSelected: ({ overlay }) => { selected.value = overlay.id },
  onDeselected: ({ overlay }) => { if (selected.value === overlay.id) selected.value = '' },
}

// 按当前的复权方式和周期，把保存的线重新画到图上。
function renderDrawings() {
  if (!chart) return
  redrawing = true
  chart.removeOverlay({ groupId: DRAW_GROUP })
  pendingId = null
  tool.value = ''
  selected.value = ''
  confirmingClear.value = false
  const bars = result.value?.bars ?? []
  if (bars.length && drawings.length) {
    chart.createOverlay(drawingOverlays(drawings, bars).map((item) => ({ ...item, groupId: DRAW_GROUP, ...drawingEvents })))
  }
  redrawing = false
  drawingCount.value = drawings.length
}

// 图上的线有变化：换算成保存用的形式，稍后保存。
function commitDrawings(removedId = null) {
  if (!chart || !canDraw.value) return
  const overlays = chart.getOverlays({ groupId: DRAW_GROUP }).filter((item) => item.id !== removedId && item.id !== pendingId)
  drawings = storedDrawings(overlays, result.value.bars)
  drawingCount.value = drawings.length
  drawingNote.value = ''
  unsaved = { symbol: props.symbol, drawings }
  clearTimeout(saveTimer)
  saveTimer = setTimeout(flushDrawings, SAVE_DELAY)
}

async function flushDrawings() {
  clearTimeout(saveTimer)
  if (!unsaved) return
  const { symbol, drawings: payload } = unsaved
  unsaved = null
  try {
    await saveChartDrawings(symbol, payload)
  } catch (e) {
    if (symbol !== props.symbol) return
    drawingNote.value = e.status === 404 && e.data?.detail === 'Not Found'
      ? '后端服务还没有保存画线的接口，请重启后端；现在画的线刷新后会消失。' : `画线没有保存成功：${e.message || '请稍后重试'}`
  }
}

async function loadDrawings() {
  const current = ++drawingsRequest
  drawings = []
  drawingsReady.value = false
  drawingNote.value = ''
  renderDrawings()
  try {
    const saved = (await chartDrawings(props.symbol)).drawings
    if (current !== drawingsRequest) return
    drawings = saved
    drawingsReady.value = true
  } catch (e) {
    if (current !== drawingsRequest) return
    // 旧版后端没有这个接口：仍然可以画，只是保存不了。其他错误时不让画，避免覆盖已经保存的线。
    if (e.status === 404 && e.data?.detail === 'Not Found') drawingsReady.value = true
    else drawingNote.value = `读取画线失败：${e.message || '请稍后重试'}`
  }
  // 行情还没读完时先不画：读完后 draw() 会按新的 K 线画出来。
  if (!loading.value) renderDrawings()
}

function useTool(name) {
  if (!chart || !canDraw.value) return
  const active = tool.value
  if (pendingId) chart.removeOverlay({ id: pendingId })
  drawingNote.value = ''
  if (active === name) return
  if (drawingCount.value >= MAX_DRAWINGS) {
    drawingNote.value = `每只股票最多保存 ${MAX_DRAWINGS} 条画线，请先删除一些。`
    return
  }
  pendingId = chart.createOverlay({ name, groupId: DRAW_GROUP, ...drawingEvents })
  tool.value = pendingId ? name : ''
}
function removeSelected() {
  if (selected.value) chart?.removeOverlay({ id: selected.value })
}
function clearDrawings() {
  if (!confirmingClear.value) {
    confirmingClear.value = true
    return
  }
  redrawing = true
  chart?.removeOverlay({ groupId: DRAW_GROUP })
  redrawing = false
  pendingId = null
  tool.value = ''
  selected.value = ''
  confirmingClear.value = false
  commitDrawings()
}

// 把某一天移到图表中间，供父组件在点击成交记录时调用。
function focus(date) {
  const index = shown.findIndex((bar) => bar.date >= date)
  if (!chart || index < 0) return
  const { from, to } = chart.getVisibleRange()
  chart.scrollToDataIndex(Math.min(shown.length - 1, index + Math.floor((to - from) / 2)))
}
defineExpose({ focus })

function show(data) {
  result.value = data
  draw()
  emit('loaded', data)
}

async function load() {
  const current = ++request
  loading.value = true
  error.value = ''
  missing.value = false
  try {
    const data = await localMarketBars(props.symbol, adjust.value)
    if (current === request) show(data)
  } catch (e) {
    if (current !== request) return
    show(null)
    // 旧版后端没有这个接口，同样返回 404（detail 为 "Not Found"），不能当作“没有行情”。
    if (e.status === 404 && e.data?.detail === 'Not Found') error.value = '后端服务还没有K线接口，请重启后端后重试。'
    else if (e.status === 404) missing.value = true
    else error.value = e.message || '读取K线失败'
  } finally {
    if (current === request) loading.value = false
  }
}

function setPeriod(key) {
  if (period.value === key) return
  period.value = key
  range.value = DEFAULT_RANGE[key]
  draw()
}
function setRange(key) {
  range.value = key
  applyRange()
}
function setSub(key) {
  sub.value = key
  chart?.removeIndicator({ paneId: SUB_PANE })
  if (key !== 'none') chart?.createIndicator({ name: key, paneId: SUB_PANE, precision: SUBS.find((item) => item.key === key).precision })
}
function setAdjust(key) {
  if (adjust.value === key) return
  adjust.value = key
  load()
}

onMounted(() => {
  chart = init(container.value, {
    locale: 'zh-CN',
    styles: theme.value,
    formatter: { formatBigNumber: formatVolume },
    thousandsSeparator: { sign: '' },
    layout: { barSpaceLimit: { min: MIN_BAR_SPACE, max: MAX_BAR_SPACE } },
  })
  chart.setStyles(chartStyles())
  chart.createIndicator({ name: 'MA', calcParams: [5, 10, 20], paneId: 'candle_pane' }, true)
  chart.createIndicator({ name: 'VOL', calcParams: [5, 10] })
  // 图表库自带的成交量图例写的是英文 VOLUME，换成中文。
  const [volume] = chart.getIndicators({ name: 'VOL' })
  chart.overrideIndicator({ name: 'VOL', figures: volume.figures.map((figure) => (figure.key === 'volume' ? { ...figure, title: '成交量: ' } : figure)) })
  setSub(sub.value)
  // 数据由本组件读取；图表只取当前已读到的全部 K 线，不再分页请求。
  chart.setDataLoader({ getBars: ({ callback }) => callback(toCandles(shown), false) })
  chart.setSymbol({ ticker: props.symbol, pricePrecision: 2, volumePrecision: 0 })
  chart.setPeriod({ type: period.value, span: 1 })
  observer = new ResizeObserver(([entry]) => {
    chart?.resize()
    const next = Math.round(entry.contentRect.width)
    if (next === width) return
    width = next
    chart?.setStyles(chartStyles())
    applyRange()
  })
  observer.observe(container.value)
  load()
  loadDrawings()
})
onBeforeUnmount(() => {
  ++request
  ++drawingsRequest
  flushDrawings()
  observer?.disconnect()
  if (chart) dispose(chart)
  chart = null
})
watch(() => props.symbol, () => {
  // 上一只股票还没保存的画线先保存，再读新的。
  flushDrawings()
  load()
  loadDrawings()
})
watch(theme, applyTheme)
watch(() => props.trades, drawTrades)
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center gap-x-5 gap-y-2">
      <div v-for="group in controls" :key="group.label" class="flex flex-wrap gap-2" role="group" :aria-label="group.label">
        <button v-for="item in group.items" :key="item.key" type="button" :aria-pressed="group.active === item.key" :disabled="group.busy"
          class="rounded-full border px-3 py-1 text-xs transition disabled:opacity-50"
          :class="group.active === item.key ? 'border-indigo-400/40 bg-indigo-500/20 text-indigo-200' : 'border-white/10 bg-white/5 text-slate-300 hover:bg-white/10'"
          @click="group.select(item.key)">{{ item.label }}</button>
      </div>
    </div>
    <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2" role="group" aria-label="画线工具">
      <span class="text-xs text-slate-400">画线</span>
      <button v-for="item in DRAWING_TOOLS" :key="item.name" type="button" :aria-pressed="tool === item.name" :disabled="!canDraw"
        class="rounded-full border px-3 py-1 text-xs transition disabled:opacity-50"
        :class="tool === item.name ? 'border-indigo-400/40 bg-indigo-500/20 text-indigo-200' : 'border-white/10 bg-white/5 text-slate-300 hover:bg-white/10'"
        @click="useTool(item.name)">{{ item.label }}</button>
      <button v-if="selected" type="button" class="rounded-full border border-rose-400/30 px-3 py-1 text-xs text-rose-300 hover:bg-rose-400/10" @click="removeSelected">删除选中的线</button>
      <button v-if="drawingCount" type="button" class="px-1 py-1 text-xs text-slate-400 hover:text-slate-200" @click="clearDrawings" @blur="confirmingClear = false">
        {{ confirmingClear ? `确认清除 ${drawingCount} 条画线？` : '清除全部' }}
      </button>
    </div>
    <!-- 提示单独占一行并保留高度：出现或消失时图表不会上下跳动。 -->
    <p class="mt-1 min-h-[2rem] text-xs sm:min-h-[1rem]" :class="drawingNote ? 'text-amber-300' : 'text-slate-400'" :role="drawingNote ? 'alert' : 'status'">{{ drawingHint }}</p>
    <div class="relative mt-2 h-[420px] sm:h-[620px]">
      <div ref="container" class="h-full w-full" :class="{ invisible: !!message }" role="img" :aria-label="`${symbol} K线图`" />
      <p v-if="message" class="absolute inset-0 flex items-center justify-center px-4 text-center text-sm"
        :class="error ? 'text-rose-300' : 'text-slate-400'" :role="error ? 'alert' : 'status'">
        <span>{{ message }} <button v-if="error" type="button" class="underline" @click="load">重试</button></span>
      </p>
    </div>
    <p v-if="caption" class="mt-2 text-xs text-slate-400">{{ caption }}</p>
    <p v-if="marked" class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
      <span v-for="item in LEGEND" :key="item.label" class="inline-flex items-center gap-1.5">
        <span class="inline-block h-2.5 rounded-sm" :class="item.wide ? 'w-5' : 'w-2.5'" :style="{ backgroundColor: item.color }" />{{ item.label }}
      </span>
      <span>已标出 {{ marked.shown }} 条记录<template v-if="marked.missing">；{{ marked.missing }} 条记录当天没有K线，未标出</template></span>
    </p>
  </div>
</template>
