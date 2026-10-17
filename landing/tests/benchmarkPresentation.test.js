import assert from 'node:assert/strict'
import test from 'node:test'
import { benchmarkCards, benchmarkChoices, benchmarkNote, benchmarkSeries } from '../src/workspace/benchmarkPresentation.js'

const benchmark = {
  symbol: '000300.SH', name: '沪深 300', comparable: true,
  strategy_curve: [0, 4, 23.03], benchmark_curve: [0, -1.2, 21.19],
  benchmark_return: 21.19, excess_return: 1.84, benchmark_max_drawdown: 10.49,
  beta: 0.57, alpha: 10.52, information_ratio: 0.11, tracking_error: 12.84,
}

test('四张卡片说明基准收益、超额收益、Beta 和 Alpha，正负号和颜色跟着数值走', () => {
  const cards = benchmarkCards(benchmark)
  assert.deepEqual(cards.map((card) => [card.label, card.value]), [
    ['沪深 300 同期收益', '+21.19%'], ['超额收益', '+1.84%'], ['Beta', '0.57'], ['年化 Alpha', '+10.52%'],
  ])
  assert.equal(cards[0].sub, '同期最大回撤 10.49%')
  assert.equal(cards[2].sub, '基准涨跌 1%，策略平均跟着变动 0.57%')
  assert.equal(cards[1].tone, 'text-emerald-300')
  const losing = benchmarkCards({ ...benchmark, excess_return: -3.05, alpha: -7.92 })
  assert.deepEqual([losing[1].value, losing[1].tone, losing[3].value, losing[3].tone], ['-3.05%', 'text-rose-300', '-7.92%', 'text-rose-300'])
})

test('算不出来的指标显示占位符，不显示成 0', () => {
  const cards = benchmarkCards({ ...benchmark, beta: null, alpha: null, benchmark_max_drawdown: null })
  assert.deepEqual([cards[2].value, cards[2].sub, cards[3].value, cards[3].tone, cards[0].sub], ['—', '数据太少，无法计算', '—', '', ''])
  assert.equal(benchmarkNote({ ...benchmark, information_ratio: null, tracking_error: null }), '沪深 300 是价格指数，不含成分股的分红，所以基准收益略微偏低。')
})

test('两条曲线带各自的期末收益；说明里有次要指标和价格指数的提醒', () => {
  assert.deepEqual(benchmarkSeries(benchmark).map((line) => [line.label, line.end, line.points.length]), [['本策略', '+23.03%', 3], ['沪深 300', '+21.19%', 3]])
  assert.equal(benchmarkNote(benchmark), '信息比率 0.11 · 年化跟踪误差 12.84%。沪深 300 是价格指数，不含成分股的分红，所以基准收益略微偏低。')
})

test('可以选的指数来自本地行情；正在显示的基准不在其中时也列出来', () => {
  const options = [{ symbol: '000300.SH', name: '沪深 300' }, { symbol: '000905.SH', name: '中证 500' }]
  assert.deepEqual(benchmarkChoices(options, benchmark), [{ value: '000300.SH', label: '沪深 300' }, { value: '000905.SH', label: '中证 500' }])
  assert.deepEqual(benchmarkChoices([options[1]], benchmark).map((item) => item.value), ['000300.SH', '000905.SH'])
  assert.deepEqual(benchmarkChoices(undefined, null), [])
})

test('基准行情没有覆盖整个区间时不比较，只说明原因；没有基准时什么都不显示', () => {
  const late = { symbol: '000300.SH', name: '沪深 300', comparable: false, benchmark_start: '2022-01-04' }
  assert.deepEqual([benchmarkCards(late), benchmarkSeries(late)], [[], []])
  assert.equal(benchmarkNote(late), '沪深 300 的本地行情从 2022-01-04 开始，没有覆盖整个回测区间，所以不做比较。可以在「数据更新」里补充基准指数的行情。')
  const stopped = { symbol: '000905.SH', name: '中证 500', comparable: false, benchmark_end: '2025-06-30' }
  assert.equal(benchmarkNote(stopped), '中证 500 的本地行情只到 2025-06-30，没有覆盖整个回测区间，所以不做比较。可以在「数据更新」里补充基准指数的行情。')
  assert.deepEqual([benchmarkCards(null), benchmarkSeries(null), benchmarkNote(null)], [[], [], ''])
})
