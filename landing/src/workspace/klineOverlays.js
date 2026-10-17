// 回测记录在 K 线上的两种图形：成交/未成交标记，以及持仓区间的底色。
// 注册是全局的，模块只会执行一次。
import { registerOverlay } from 'klinecharts'

// 橙色买入、蓝色卖出：和红涨绿跌的 K 线颜色区分开。
export const TRADE_COLORS = { buy: '#f97316', sell: '#3b82f6', reject: '#94a3b8', holding: 'rgba(99, 102, 241, 0.14)' }
const LABELS = { buy: '买', sell: '卖', reject: '拒' }

registerOverlay({
  name: 'fqTradeMark',
  totalStep: 2,
  needDefaultPointFigure: false,
  needDefaultXAxisFigure: false,
  needDefaultYAxisFigure: false,
  // points[0] 是成交价，points[1] 是这根 K 线的最低价（买）或最高价（卖）。
  createPointFigures: ({ chart, overlay, coordinates }) => {
    const { kind, buy } = overlay.extendData
    const color = TRADE_COLORS[kind]
    const { bar } = chart.getBarSpace()
    const x = coordinates[0].x
    const edge = coordinates[1].y
    // 买入标在 K 线下方、箭头朝上；卖出标在上方、箭头朝下。
    const direction = buy ? 1 : -1
    // 未成交标记离 K 线更远一些，和同一天的成交标记错开。
    const offset = kind === 'reject' ? 30 : 4
    const tip = edge + direction * offset
    const base = tip + direction * 8
    const figures = [{
      type: 'polygon',
      attrs: { coordinates: [{ x, y: tip }, { x: x - 5, y: base }, { x: x + 5, y: base }] },
      styles: kind === 'reject' ? { style: 'stroke', borderColor: color } : { style: 'fill', color },
      ignoreEvent: true,
    }]
    if (kind !== 'reject') {
      // 成交价上的短横线，和 K 线对照就能看出成交在当天价格区间的什么位置。
      const half = Math.max(5, bar / 2 + 2)
      figures.push({
        type: 'line',
        attrs: { coordinates: [{ x: x - half, y: coordinates[0].y }, { x: x + half, y: coordinates[0].y }] },
        styles: { color, size: 2 },
        ignoreEvent: true,
      })
    }
    // K 线太密时不写字，避免文字叠在一起。
    if (bar >= 4) {
      figures.push({
        type: 'text',
        attrs: { x, y: base + direction * 2, text: LABELS[kind], align: 'center', baseline: buy ? 'top' : 'bottom' },
        styles: { color, size: 11, backgroundColor: 'transparent', borderSize: 0, paddingLeft: 0, paddingRight: 0, paddingTop: 0, paddingBottom: 0 },
        ignoreEvent: true,
      })
    }
    return figures
  },
})

registerOverlay({
  name: 'fqHoldingSpan',
  totalStep: 3,
  needDefaultPointFigure: false,
  needDefaultXAxisFigure: false,
  needDefaultYAxisFigure: false,
  createPointFigures: ({ chart, coordinates, bounding }) => {
    const half = chart.getBarSpace().bar / 2
    const left = coordinates[0].x - half
    return {
      type: 'rect',
      attrs: { x: left, y: 0, width: coordinates[1].x + half - left, height: bounding.height },
      styles: { style: 'fill', color: TRADE_COLORS.holding },
      ignoreEvent: true,
    }
  },
})
