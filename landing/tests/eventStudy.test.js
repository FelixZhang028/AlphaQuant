import test from 'node:test'
import assert from 'node:assert/strict'
import { compareRows, decodePreset, defaultCondition, diffText, encodePreset, headline, histogramBars, statesFromFacts, tone } from '../src/workspace/eventStudy.js'

const kinds = [
  { type: 'ret', days: [5, 20, 60], directions: [], compare: true, example: -20 },
  { type: 'ma_cross', days: [20, 60], directions: [{ value: 'up' }, { value: 'down' }], compare: false },
  { type: 'pe', days: [], directions: [], compare: true, example: 15 },
]

test('新加条件的默认值；条件写进链接再读出来', () => {
  assert.deepEqual(defaultCondition(kinds[0]), { type: 'ret', days: 20, op: '<=', value: -20 })
  assert.deepEqual(defaultCondition(kinds[1]), { type: 'ma_cross', days: 20, direction: 'up' })
  assert.deepEqual(defaultCondition(kinds[2]), { type: 'pe', op: '>=', value: 15 })
  const conditions = [{ type: 'ret', days: 20, op: '<=', value: -15 }, { type: 'ma_cross', days: 60, direction: 'up' }]
  const text = encodePreset(conditions)
  assert.equal(text, 'ret:20::<=:-15|ma_cross:60:up::')
  assert.deepEqual(decodePreset(text, kinds), conditions)
  assert.deepEqual(decodePreset('nope:1:::|pe:::<=:30', kinds), [{ type: 'pe', op: '<=', value: 30 }])   // 不认识的去掉
  assert.deepEqual(decodePreset('', kinds), [])
})

test('满足条件和全部交易日的对照、一句话说明', () => {
  const horizon = { events: { count: 120, mean: 0.05, median: 0.03, up_share: 0.62, p25: -0.03, p75: 0.12 },
    all: { count: 9000, mean: 0.01, median: -0.005, up_share: 0.47, p25: -0.07, p75: 0.06 }, excess: { mean: -0.002 } }
  const rows = compareRows(horizon)
  assert.deepEqual(rows.map((r) => r.label), ['平均涨跌', '中位数', '上涨的比例', '中间一半落在'])
  assert.equal(rows[0].event, '+5.00%')
  assert.equal(diffText(rows[0]), '+4.00%')
  assert.equal(diffText(rows[2]), '+15.0 个百分点')
  assert.equal(diffText(rows[3]), '')
  assert.deepEqual(compareRows({ events: { count: 0 } }), [])
  const result = { start: '2016-02-29', end: '2026-10-19', scope: '全市场', events: 3311, stocks: 1401, main_horizon: 20, horizons: { 20: horizon } }
  assert.equal(headline(result), '2016-02-29 至 2026-10-19，全市场共出现 3,311 次（1,401 只股票）；之后 20 个交易日平均 +5.00%，全部交易日平均 +1.00%；扣掉同一天全部股票的平均以后是 -0.20%。')
  assert.equal(headline({ ...result, events: 0 }), '这段时间里没有满足条件的情况。')
  assert.equal(tone(0.01), 'text-rose-300')
  assert.equal(tone(-0.01), 'text-emerald-300')
})

test('分布图柱子的高度', () => {
  const bars = histogramBars({ labels: ['跌', '平', '涨'], events: [0.2, 0.4, 0.4], all: [0.1, 0.8, 0.1] })
  assert.deepEqual(bars.map((b) => [b.eventHeight, b.allHeight]), [[25, 13], [50, 100], [50, 13]])
})

test('从 AI研究员的数据表推出这只股票现在的状态，每个都带着事件研究的条件', () => {
  const facts = [{ key: 'ret_20d', value: -0.23 }, { key: 'from_high_250d', value: -0.37 }, { key: 'ma60_gap', value: -0.05 },
    { key: 'amount_ratio', value: 2.6 }, { key: 'pe_ttm', value: 12.3 }, { key: 'profit_growth', value: 0.8 }]
  const states = statesFromFacts(facts)
  assert.deepEqual(states.map((s) => s.text), ['近 20 个交易日跌了 23%', '距近一年最高价 -37%', '收盘价在 60 日均线下方', '当日成交额是近 20 日平均的 2.6 倍', '市盈率 12.3'])
  assert.deepEqual(states[1].conditions, [{ type: 'from_high', op: '<=', value: -30 }])
  assert.deepEqual(states[4].conditions, [{ type: 'pe', op: '<=', value: 15 }])
  assert.deepEqual(statesFromFacts([{ key: 'ret_20d', value: 0.02 }]), [])
  assert.equal(statesFromFacts([{ key: 'pe_ttm', value: 80 }])[0].conditions[0].op, '>=')
})
