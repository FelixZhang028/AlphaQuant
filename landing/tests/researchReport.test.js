import test from 'node:test'
import assert from 'node:assert/strict'
import { checkCounts, eventMarkers, pct, priceSeries, signedPct, sortedChecks, trendTone, valuationSeries, yi } from '../src/workspace/researchReport.js'

test('数字格式：百分比、带符号、亿元，没有数据时是“—”', () => {
  assert.equal(pct(0.1234), '12.3%')
  assert.equal(signedPct(-0.05), '-5.0%')
  assert.equal(signedPct(0.05), '+5.0%')
  assert.equal(yi(2.5e10), '250 亿')
  assert.equal(yi(3.4e9), '34 亿')
  assert.equal(pct(null), '—')
})

test('留意清单：需要留意的排在前面，数一数各有几项', () => {
  const checks = [{ key: 'a', state: 'ok' }, { key: 'b', state: 'warn' }, { key: 'c', state: 'unknown' }, { key: 'd', state: 'warn' }]
  assert.deepEqual(sortedChecks(checks).map((c) => c.key), ['b', 'd', 'c', 'a'])
  assert.deepEqual(checkCounts(checks), { ok: 1, warn: 2, unknown: 1 })
  assert.equal(trendTone('连续下降'), 'text-amber-300')
})

test('事件标在对应的交易日；周末的事件标在下一个交易日', () => {
  const prices = [['2026-10-09', 10, 9.8, 9.5], ['2026-10-12', 10.2, 9.9, 9.6], ['2026-10-13', 10.1, 10, 9.7]]
  const { labels, series } = priceSeries(prices)
  assert.equal(series.length, 3)
  const marks = eventMarkers(labels, [{ date: '2026-10-11', kind: 'report', text: '发布三季报' }, { date: '2026-10-20', kind: 'action', text: '晚了' }])
  assert.deepEqual(marks, [{ index: 1, kind: 'report', text: '2026-10-11 发布三季报' }])
})

test('估值图带三条分位线', () => {
  const view = valuationSeries({ points: [['2026-01-02', 12, 1.5], ['2026-01-09', 13, 1.6]], bands: { pe_ttm: { p20: 10, p50: 12, p80: 14, current: 13, share: 0.6 } } }, 'pe_ttm')
  assert.deepEqual(view.series[0].values, [12, 13])
  assert.equal(view.bands.length, 3)
  assert.deepEqual(valuationSeries({ points: [['2026-01-02', 12, 1.5]], bands: {} }, 'pb_mrq').series[0].values, [1.5])
})
