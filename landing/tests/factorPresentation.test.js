import test from 'node:test'
import assert from 'node:assert/strict'
import { ALPHA101_NOTE, directionText, directionTone, factorNote, factorSummary, historyText } from '../src/workspace/factorPresentation.js'

const alpha = {
  name: 'alpha101_001', display_name: '收益为负时的波动与价格的高点位置', source: 'Alpha101', direction: 1, min_history: 25,
  description: '收益为负时的波动与价格的高点位置。按原公式计算，正向输出；A股有效性需独立评估。',
  formula: 'rank(Ts_ArgMax(SignedPower(((returns < 0) ? stddev(returns, 20) : close), 2.), 5)) - 0.5',
}

test('方向写正向 / 反向，正向绿色、反向红色；历史长度带单位', () => {
  assert.equal(directionText(1), '正向')
  assert.equal(directionText(-1), '反向')
  assert.equal(directionText(0), '—')
  assert.equal(directionTone(1), 'text-emerald-300')
  assert.equal(directionTone(-1), 'text-rose-300')
  assert.equal(directionTone(0), 'text-slate-400')
  assert.equal(historyText(25), '25 天')
  assert.equal(historyText(null), '—')
})

test('Alpha101 不再每行重复同一句话，说明和名字一样时显示公式', () => {
  assert.deepEqual(factorSummary(alpha), { text: alpha.formula, formula: true })
  const builtin = { name: 'mom_20', display_name: '20 日动量', description: '过去 20 个交易日的涨跌幅', formula: 'close / close.shift(20) - 1' }
  assert.deepEqual(factorSummary(builtin), { text: '过去 20 个交易日的涨跌幅', formula: false })
  assert.deepEqual(factorSummary({ name: 'x', display_name: 'x' }), { text: '—', formula: false })
})

test('详情：专门写的说明优先，Alpha101 和自定义因子各有通用说明', () => {
  assert.deepEqual(factorNote(alpha, {}), { meaning: '收益为负时的波动与价格的高点位置。', usage: ALPHA101_NOTE })
  const special = { meaning: '专门的说明', usage: '专门的用法' }
  assert.equal(factorNote(alpha, { alpha101_001: special }), special)
  assert.match(factorNote({ name: 'my', category: '自定义', description: '' }).usage, /自定义因子/)
  assert.doesNotMatch(factorNote({ name: 'mom_20', category: '动量', description: '动量' }).usage, /自定义因子/)
  assert.equal(factorNote(null), null)
})
