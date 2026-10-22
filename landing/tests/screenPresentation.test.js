import assert from 'node:assert/strict'
import test from 'node:test'
import { changeText, conditionValues, formatIndicator, screenSummary } from '../src/workspace/screenPresentation.js'

test('指标数值按单位显示', () => {
  assert.equal(formatIndicator('close', 1309.69), '1309.69')
  assert.equal(formatIndicator('moving_average', 1298.2093), '1298.21')
  assert.equal(formatIndicator('return', 0.0290237), '+2.90%')
  assert.equal(formatIndicator('drawdown', -0.12), '-12.00%')
  assert.equal(formatIndicator('volatility', 0.243), '24.3%')
  assert.equal(formatIndicator('rsi', 65.557), '65.6')
  assert.equal(formatIndicator('average_amount', 3.418e9), '34.18 亿')
  assert.equal(formatIndicator('average_amount', 5.5e7), '5500 万')
  assert.equal(formatIndicator('rsi', null), '—')
  assert.equal(changeText(-0.0166606), '-1.67%')
  assert.equal(changeText(0.008), '+0.80%')
})

test('条件两边的数值：固定数值按左边指标的单位显示', () => {
  const result = { condition_indicators: [{ left: 'close', right: 'moving_average' }, { left: 'return', right: null }] }
  const item = { conditions: [{ left: 42.28, right: 40.3668 }, { left: 0.08, right: 0.05 }] }
  assert.deepEqual(conditionValues(result, item, 0), { left: '42.28', right: '40.37' })
  assert.deepEqual(conditionValues(result, item, 1), { left: '+8.00%', right: '+5.00%' })
})

test('结果概括', () => {
  assert.equal(screenSummary({ scope: 'pool', trade_date: '2026-10-21', checked: 10, matched: 3, shown: 3 }),
    '按 2026-10-21 收盘后的数据，在你的股票池 10 只股票里，有 3 只符合条件')
  assert.equal(screenSummary({ scope: 'market', trade_date: '2026-10-21', checked: 4801, matched: 1057, shown: 100 }),
    '按 2026-10-21 收盘后的数据，在全市场 4,801 只股票里，有 1,057 只符合条件，按排序显示前 100 只')
  assert.equal(screenSummary(null), '')
})

test('条件选股和新建规则策略之间交接条件：取走一次就没有了', async () => {
  const store = new Map()
  globalThis.sessionStorage = { setItem: (k, v) => store.set(k, v), getItem: (k) => store.get(k) ?? null, removeItem: (k) => store.delete(k) }
  const { handOffRules, takeHandedRules } = await import('../src/workspace/ruleHandoff.js')
  handOffRules({ name: '动量', entry_rules: [] })
  assert.deepEqual(takeHandedRules(), { name: '动量', entry_rules: [] })
  assert.equal(takeHandedRules(), null)
  delete globalThis.sessionStorage
  assert.equal(takeHandedRules(), null)          // 没有存储也不出错
})
