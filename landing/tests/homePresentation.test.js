import test from 'node:test'
import assert from 'node:assert/strict'
import {
  amountText, breadthShares, dailyText, greeting, industryQuestion, price, seasonShare, seasonText, signedPct, sortPool,
  sparkPath, stepsProgress, todayText, tone, whenText,
} from '../src/workspace/homePresentation.js'

test('问候语和日期', () => {
  assert.equal(greeting(new Date(2026, 9, 20, 8)), '早上好')
  assert.equal(greeting(new Date(2026, 9, 20, 15)), '下午好')
  assert.equal(greeting(new Date(2026, 9, 20, 21)), '晚上好')
  assert.equal(todayText(new Date(2026, 9, 20)), '2026年10月20日 星期二')
})

test('A 股习惯：红涨绿跌；数字格式', () => {
  assert.equal(tone(0.01), 'text-rose-300')
  assert.equal(tone(-0.01), 'text-emerald-300')
  assert.equal(tone(0), 'text-slate-300')
  assert.equal(tone(null), 'text-slate-300')
  assert.equal(signedPct(0.0039), '+0.39%')
  assert.equal(signedPct(-0.036), '-3.60%')
  assert.equal(signedPct(null), '—')
  assert.equal(price(3730.92), '3,730.92')
  assert.equal(amountText(1433207865404), '1.43 万亿')
  assert.equal(amountText(8.5e10), '850 亿')
})

test('小走势图和涨跌分布', () => {
  assert.equal(sparkPath([1, 2, 3], 100, 30), 'M0.0,30.0 L50.0,15.0 L100.0,0.0')
  assert.equal(sparkPath([5]), '')
  assert.equal(sparkPath([2, 2], 100, 30), 'M0.0,30.0 L100.0,30.0')
  assert.deepEqual(breadthShares({ up: 2201, flat: 150, down: 2860 }), { up: 42.2, flat: 2.9, down: 54.9 })
  assert.equal(breadthShares({ up: 0, flat: 0, down: 0 }), null)
})

test('股票池排序：没有行情的放最后', () => {
  const rows = [{ symbol: 'a', change: 0.01 }, { symbol: 'b', change: null }, { symbol: 'c', change: 0.05 }, { symbol: 'd', change: -0.02 }]
  assert.deepEqual(sortPool(rows, 'change', true).map((r) => r.symbol), ['c', 'a', 'd', 'b'])
  assert.deepEqual(sortPool(rows, 'change', false).map((r) => r.symbol), ['d', 'a', 'c', 'b'])
  assert.deepEqual(sortPool(rows).map((r) => r.symbol), ['a', 'b', 'c', 'd'])
})

test('最近的研究的时间', () => {
  const now = new Date(2026, 9, 20, 15, 0)
  assert.equal(whenText(new Date(2026, 9, 20, 9, 5).toISOString(), now), '今天 09:05')
  assert.equal(whenText(new Date(2026, 9, 19, 22, 30).toISOString(), now), '昨天 22:30')
  assert.equal(whenText(new Date(2026, 8, 3).toISOString(), now), '9月3日')
  assert.equal(whenText(new Date(2025, 0, 2).toISOString(), now), '2025-1-2')
  assert.equal(whenText('not a date', now), '')
})

test('新手任务、数据日历和行业的提问', () => {
  const steps = [{ key: 'pool', done: true }, { key: 'strategy', done: false }, { key: 'backtest', done: false }]
  assert.deepEqual(stepsProgress(steps), { done: 1, total: 3, finished: false, next: steps[1] })
  assert.equal(stepsProgress(steps.map((s) => ({ ...s, done: true }))).finished, true)
  assert.equal(stepsProgress([]).finished, false)
  assert.equal(dailyText({ enabled: true, time: '18:30', data_date: '2026-10-19' }), '行情更新到 2026-10-19 · 每个交易日 18:30 以后自动更新')
  assert.equal(dailyText({ enabled: false, data_date: null }), '还没有行情数据 · 自动更新已关闭')
  const season = { period: '2026三季报', deadline: '2026-10-31', published: 105, listed: 5211, days_left: 11 }
  assert.equal(seasonText(season), '2026三季报最晚 2026-10-31 公布（还有 11 天），已公布 105 家')
  assert.equal(seasonShare(season), 2)
  assert.equal(industryQuestion('银行'), '银行这个行业现在的估值和财务情况怎么样？')
})
