import assert from 'node:assert/strict'
import test from 'node:test'
import { summarizeDataOverview } from '../src/workspace/dataPresentation.js'
import { allItems, groups, navigationItem } from '../src/workspace/modules.js'

const complete = () => ({
  configured_symbol_count: 2, coverage_ratio: 1, unknown_status_rows: 0,
  per_symbol: [
    { symbol: '000001', rows: 10, end_date: '2025-01-10' },
    { symbol: '000002', rows: 8, end_date: '2025-01-08' },
  ],
})

test('历史覆盖完整只表示已保存区间，截止日期取最早一只股票', () => {
  const result = summarizeDataOverview(complete())
  assert.equal(result.state, 'covered')
  assert.equal(result.through, '2025-01-08')
  assert.match(result.hint, /不代表行情已更新到最新交易日/)
})

test('读取失败或刷新中不能用旧的完整数据给出就绪结论', () => {
  assert.equal(summarizeDataOverview(complete(), { error: '读取失败' }).state, 'error')
  assert.equal(summarizeDataOverview(complete(), { loading: true }).state, 'loading')
})

test('缺失股票或部分交易日不能显示覆盖完整，即使百分比舍入为100%', () => {
  const missing = complete()
  missing.per_symbol[1].rows = 0
  const result = summarizeDataOverview(missing)
  assert.equal(result.state, 'incomplete')
  assert.equal(result.missing, 1)
  assert.equal(summarizeDataOverview({ ...complete(), coverage_ratio: 0.999999 }).state, 'incomplete')
})

test('未知交易状态不能被覆盖率100%掩盖', () => {
  assert.equal(summarizeDataOverview({ ...complete(), unknown_status_rows: 3 }).state, 'warning')
})

test('缺失、负数或无效质量指标不能显示正常', () => {
  for (const unknown_status_rows of [undefined, null, -1, 'invalid']) {
    assert.equal(summarizeDataOverview({ ...complete(), unknown_status_rows }).state, 'unknown')
  }
  assert.equal(summarizeDataOverview({ ...complete(), coverage_ratio: 1.1 }).state, 'unknown')
})

test('空股票池和无本地行情显示不同下一步', () => {
  assert.equal(summarizeDataOverview({ ...complete(), configured_symbol_count: 0, per_symbol: [] }).state, 'empty')
  assert.equal(summarizeDataOverview({ ...complete(), per_symbol: [], coverage_ratio: 0 }).state, 'missing')
})

test('菜单收敛后，XTick和风险管理的原直达链接仍能定位到正确分组', () => {
  const data = groups.find((group) => group.label === '数据管理')
  assert.deepEqual(data.items.map((item) => item.key), ['data-management', 'data-update', 'universe'])
  for (const key of ['xtick-data', 'risk-management']) assert.ok(allItems.some((item) => item.key === key))
  assert.equal(navigationItem('xtick-data').key, 'data-management')
  assert.equal(navigationItem('risk-management').key, 'backtest-review')
})
