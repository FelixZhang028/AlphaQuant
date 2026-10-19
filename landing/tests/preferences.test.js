import test from 'node:test'
import assert from 'node:assert/strict'
import { backtestDefaults, periodFor } from '../src/workspace/preferences.js'

test('默认回测区间截止到今天，往前推几年', () => {
  assert.deepEqual(periodFor(3, new Date(2026, 9, 19)), { from_date: '2023-10-19', to_date: '2026-10-19' })
  assert.deepEqual(periodFor(1, new Date(2028, 1, 29)), { from_date: '2027-02-28', to_date: '2028-02-29' })
})

test('回测表单的默认值来自个人设置', () => {
  const defaults = backtestDefaults({ initial_capital: 500000, max_positions: 20, rebalance: 'monthly', period_years: 2 }, new Date(2026, 0, 5))
  assert.deepEqual(defaults, { initial_capital: 500000, max_positions: 20, rebalance: 'monthly', from_date: '2024-01-05', to_date: '2026-01-05' })
})
