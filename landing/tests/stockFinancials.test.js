import test from 'node:test'
import assert from 'node:assert/strict'
import { arrow, chartSeries, coverageText, emptyText, latestCards, points, shares } from '../src/workspace/stockFinancials.js'

const latest = {
  period: '2026半年报', revenue: 92.3e9, revenue_yoy: null, net_profit: 46e9, profit_yoy: -0.02,
  gross_margin: 0.8956, net_margin: 0.5075, roe: 0.1795, debt_ratio: 0.152, last_year: '2025半年报',
  changes: { gross_margin: -0.012, net_margin: 0, roe: null, debt_ratio: 0.01 },
  missing: { revenue_yoy: '本地没有去年同期的营收，算不出同比' },
}

test('数字格式：股本按亿股，比率的变化按百分点，箭头只表示高低', () => {
  assert.equal(shares(12.5e8), '12.5 亿股')
  assert.equal(points(-0.012), '-1.2 个百分点')
  assert.equal(points(0.01), '+1.0 个百分点')
  assert.equal(arrow(0.01), '↑')
  assert.equal(arrow(-0.01), '↓')
  assert.equal(arrow(0), '→')
  assert.equal(arrow(null), '')
})

test('最新一期的卡片：金额配同比，比率配和去年同期的差；没有数据时说明原因', () => {
  const cards = Object.fromEntries(latestCards(latest).map((card) => [card.key, card]))
  assert.equal(cards.revenue.value, '923 亿')
  assert.equal(cards.revenue.known, false)
  assert.equal(cards.revenue.changeText, '—')
  assert.equal(cards.revenue.changeReason, '本地没有去年同期的营收，算不出同比')
  assert.equal(cards.net_profit.changeText, '-2.0%')
  assert.equal(cards.gross_margin.changeText, '-1.2 个百分点')
  assert.equal(cards.roe.changeReason, '去年同期没有这一项')
  assert.equal(cards.gross_margin.changeReason, '')
  assert.equal(latestCards({ ...latest, last_year: null, changes: {} }).find((c) => c.key === 'debt_ratio').changeReason, '本地没有去年同期的财报')
  assert.deepEqual(latestCards(null), [])
})

test('趋势图按时间从旧到新；累计的数字提示每年一季度从零算起', () => {
  const rows = [{ period: '2026半年报', net_profit: 46e9, profit_yoy: -0.02 }, { period: '2026一季报', net_profit: 28e9, profit_yoy: null }]
  const growth = chartSeries(rows, 'profit_yoy')
  assert.deepEqual(growth.labels, ['2026一季报', '2026半年报'])
  assert.deepEqual(growth.series[0].values, [null, -0.02])
  assert.equal(growth.points, 1)
  assert.equal(growth.zeroLine, true)
  assert.equal(growth.note, '')
  assert.match(chartSeries(rows, 'net_profit').note, /一季度会重新从零算起/)
})

test('本地有几期；没有财报时说明原因，管理员多一句怎么更新', () => {
  assert.equal(coverageText({ periods: 4, first_period: '2025三季报', last_period: '2026半年报' }), '本地有 4 期财报（2025三季报 ～ 2026半年报）')
  assert.equal(coverageText({ periods: 1, last_period: '2026半年报' }), '本地有 1 期财报（2026半年报）')
  assert.equal(emptyText({ periods: 4 }), '')
  assert.match(emptyText({ periods: 0, empty_periods: ['2025三季报'] }, false), /数据源确认.*2025三季报.*财报季定期更新/)
  assert.match(emptyText({ periods: 0, empty_periods: [] }, true), /还没有下载到.*管理后台/)
})
