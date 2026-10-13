import assert from 'node:assert/strict'
import test from 'node:test'
import { summarizeDataOverview } from '../src/workspace/dataPresentation.js'
import { allItems, groups, navigationItem, resolveView } from '../src/workspace/modules.js'

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

test('菜单收敛后，XTick的原直达链接仍能定位到正确分组，风险管理的旧链接落到回测页', () => {
  const data = groups.find((group) => group.label === '数据管理')
  assert.deepEqual(data.items.map((item) => item.key), ['data-management', 'data-update', 'universe'])
  assert.ok(allItems.some((item) => item.key === 'xtick-data'))
  assert.equal(navigationItem('xtick-data').key, 'data-management')
  // 风控设置只保留在回测表单里；独立页面已删除。
  assert.ok(!allItems.some((item) => item.key === 'risk-management'))
  assert.equal(resolveView('risk-management'), 'backtest-review')
})

test('估值与换手率的覆盖情况用一句话说明：没有、部分、全部', async () => {
  const { indicatorSummary } = await import('../src/workspace/dataPresentation.js')
  assert.equal(indicatorSummary(null), '')
  assert.equal(indicatorSummary({ symbols: 0, missing_symbols: 5478, rows: 0, start_date: null, end_date: null }),
    '还没有下载。本地有行情的 5,478 只股票都可以补全。')
  assert.equal(indicatorSummary({ symbols: 1200, missing_symbols: 4278, start_date: '2015-01-05', end_date: '2026-10-09' }),
    '已有 1,200 只股票（2015-01-05 至 2026-10-09），还有 4,278 只没有。')
  assert.equal(indicatorSummary({ symbols: 5478, missing_symbols: 0, start_date: '2015-01-05', end_date: '2026-10-09' }),
    '本地有行情的 5,478 只股票都已覆盖（2015-01-05 至 2026-10-09）。')
})
