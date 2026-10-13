import assert from 'node:assert/strict'
import test from 'node:test'
import { DRAWING_TOOLS, drawingOverlays, storedDrawings, timestampOf } from '../src/workspace/klineDrawings.js'

// 2026-01-08 除息：之前的 K 线按 0.9 的比例显示，之后是 1。
const forward = [
  { date: '2026-01-05', factor: 0.9 }, { date: '2026-01-06', factor: 0.9 }, { date: '2026-01-07', factor: 0.9 },
  { date: '2026-01-08', factor: 1 }, { date: '2026-01-09', factor: 1 },
]
const raw = forward.map((bar) => ({ ...bar, factor: 1 }))
const point = (date, value) => ({ timestamp: timestampOf(date), value })

test('保存的是日期和不复权价格，换成不复权后线仍在同一根 K 线的同一个位置', () => {
  const drawn = [{ name: 'segment', points: [point('2026-01-06', 9), point('2026-01-09', 11)] }]
  const stored = storedDrawings(drawn, forward)
  assert.deepEqual(stored, [{ name: 'segment', points: [{ date: '2026-01-06', price: 10 }, { date: '2026-01-09', price: 11 }] }])
  assert.deepEqual(drawingOverlays(stored, raw), [{ name: 'segment', points: [point('2026-01-06', 10), point('2026-01-09', 11)] }])
  assert.deepEqual(drawingOverlays(stored, forward), drawn)
})

test('点落在没有 K 线的日期时，用之前最近一根的复权比例；早于全部 K 线时用第一根', () => {
  const stored = storedDrawings([{ name: 'rayLine', points: [point('2026-01-01', 9), point('2026-02-01', 12)] }], forward)
  assert.deepEqual(stored[0].points, [{ date: '2026-01-01', price: 10 }, { date: '2026-02-01', price: 12 }])
  // 没有行情时不换算。
  assert.deepEqual(storedDrawings([{ name: 'horizontalStraightLine', points: [point('2026-01-06', 9)] }], [])[0].points, [{ date: '2026-01-06', price: 9 }])
})

test('没画完的线、不认识的图形和无效的点不保存', () => {
  const overlays = [
    { name: 'segment', points: [point('2026-01-06', 9)] },
    { name: 'fqTradeMark', points: [point('2026-01-06', 9), point('2026-01-07', 9)] },
    { name: 'segment', points: [point('2026-01-06', 9), { value: 10 }] },
    { name: 'horizontalStraightLine', points: [point('2026-01-06', -1)] },
    { name: 'fibonacciLine', points: [point('2026-01-06', 9), point('2026-01-09', 11)] },
  ]
  assert.deepEqual(storedDrawings(overlays, forward).map((item) => item.name), ['fibonacciLine'])
  assert.deepEqual(drawingOverlays([{ name: 'circle', points: [] }, { name: 'segment', points: [{ date: '2026-01-06', price: 10 }] }], forward), [])
})

test('四种画线工具的名称和点数与后端的名单一致', () => {
  assert.deepEqual(Object.fromEntries(DRAWING_TOOLS.map((tool) => [tool.name, tool.points])),
    { segment: 2, rayLine: 2, horizontalStraightLine: 1, fibonacciLine: 2 })
})
