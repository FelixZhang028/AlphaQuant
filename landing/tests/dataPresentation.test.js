import assert from 'node:assert/strict'
import test from 'node:test'
import { summarizeDataOverview } from '../src/workspace/dataPresentation.js'
import { adminViews, allItems, groups, navigationItem, resolveView, viewFor, visibleGroups } from '../src/workspace/modules.js'

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

test('数据菜单：所有人看数据说明、股票查询和股票池；数据运维、数据检查和 XTick 只有管理员能打开', () => {
  const data = groups.find((group) => group.label === '数据')
  assert.deepEqual(data.items.map((item) => item.key), ['data-guide', 'market-lookup', 'universe', 'data-update'])
  assert.deepEqual(visibleGroups(false).find((group) => group.label === '数据').items.map((item) => item.key), ['data-guide', 'market-lookup', 'universe'])
  assert.deepEqual(visibleGroups(true).find((group) => group.label === '数据').items.map((item) => item.key), ['data-guide', 'market-lookup', 'universe', 'data-update'])
  assert.deepEqual([...adminViews].sort(), ['data-management', 'data-update', 'xtick-data'])
  for (const old of ['data-update', 'data-management', 'xtick-data']) {
    assert.equal(viewFor(old, false), 'data-guide')      // 普通用户的旧链接落到数据说明
    assert.equal(viewFor(old, true), old)
  }
  assert.equal(viewFor('market-lookup', false), 'market-lookup')
  assert.ok(allItems.some((item) => item.key === 'xtick-data'))
  assert.equal(navigationItem('xtick-data').key, 'data-update')
  assert.equal(navigationItem('data-management').key, 'data-update')
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

test('财务数据的覆盖情况用一句话说明：没有、部分、全部', async () => {
  const { fundamentalsSummary } = await import('../src/workspace/dataPresentation.js')
  assert.equal(fundamentalsSummary(null), '')
  assert.equal(fundamentalsSummary({ symbols: 0, missing_symbols: 5478, reports: 0, latest_stat_date: null }), '还没有下载。')
  assert.equal(fundamentalsSummary({ symbols: 9, missing_symbols: 5469, reports: 420, latest_stat_date: '2026-06-30' }),
    '已有 9 只股票的财报（最新报告期 2026-06-30）；本地有行情的股票里还有 5,469 只没有。')
  assert.equal(fundamentalsSummary({ symbols: 5478, missing_symbols: 0, reports: 250000, latest_stat_date: '2026-06-30' }),
    '本地有行情的 5,478 只股票都有财报（最新报告期 2026-06-30）。')
})

test('行业分类的覆盖情况用一句话说明；中性化有四种选择', async () => {
  const { industrySummary, NEUTRALIZATION_OPTIONS } = await import('../src/workspace/dataPresentation.js')
  assert.equal(industrySummary(null), '')
  assert.equal(industrySummary({ symbols: 0, missing_symbols: 5478, snapshots: 0, start_date: null, end_date: null }), '还没有下载。')
  assert.equal(industrySummary({ symbols: 5200, missing_symbols: 278, snapshots: 48, start_date: '2015-03-31', end_date: '2026-10-13' }),
    '已有 5,200 只股票的行业分类（2015-03-31 至 2026-10-13，48 个时点）；有 278 只没有分类（多数是已经退市的）。')
  assert.equal(industrySummary({ symbols: 300, missing_symbols: 0, snapshots: 2, start_date: '2026-06-30', end_date: '2026-10-13' }),
    '已有 300 只股票的行业分类（2026-06-30 至 2026-10-13，2 个时点）。')
  assert.deepEqual(NEUTRALIZATION_OPTIONS.map((option) => option.value), ['none', 'industry', 'size', 'both'])
})

test('指数成分股的覆盖情况每个指数一句话', async () => {
  const { indexConstituentsSummary } = await import('../src/workspace/dataPresentation.js')
  assert.deepEqual(indexConstituentsSummary(null), [])
  assert.deepEqual(indexConstituentsSummary([
    { symbol: '000300.SH', name: '沪深300', start_date: '2015-01-05', end_date: '2026-10-12', changes: 27, members: 300 },
    { symbol: '000016.SH', name: '上证50', start_date: null, end_date: null, changes: 0, members: 0 },
  ]), ['沪深300：2015-01-05 至 2026-10-12，名单变化过 27 次，现在 300 只。', '上证50：还没有下载。'])
})

test('行情不完整的股票用一句话说明；没有时不显示', async () => {
  const { barGapSummary } = await import('../src/workspace/dataPresentation.js')
  assert.equal(barGapSummary(null), '')
  assert.equal(barGapSummary({ symbols: 0, without_bars: 0, examples: [] }), '')
  assert.equal(barGapSummary({
    symbols: 143, without_bars: 1,
    examples: [
      { symbol: '002450.SZ', name: '康得退', expected_start: '2015-01-05', first_bar: null },
      { symbol: '002314.SZ', name: '南山控股', expected_start: '2015-01-05', first_bar: '2022-06-01' },
    ],
  }), '有 143 只股票的行情不完整：开始得比上市日期晚，或者完全没有。例如南山控股（002314.SZ）应该从 2015-01-05 开始，本地从 2022-06-01 才开始。其中 1 只完全没有行情。')
  assert.equal(barGapSummary({ symbols: 1, without_bars: 1, examples: [{ symbol: '002450.SZ', name: '', expected_start: '2015-01-05', first_bar: null }] }),
    '有 1 只股票的行情不完整：开始得比上市日期晚，或者完全没有。其中 1 只完全没有行情。')
})

test('找不到分红送转记录的复权因子变化用一句话说明', async () => {
  const { actionGapSummary } = await import('../src/workspace/dataPresentation.js')
  assert.equal(actionGapSummary(null), '')
  assert.equal(actionGapSummary({ changes: 0, symbols: 0, to_check: 0 }), '')
  assert.equal(actionGapSummary({ changes: 973, symbols: 428, to_check: 428 }),
    '有 973 次复权因子变化找不到分红送转记录（428 只股票）。其中 428 只股票还可以向 BaoStock 补查记录。')
  assert.equal(actionGapSummary({ changes: 250, symbols: 235, to_check: 0 }),
    '有 250 次复权因子变化找不到分红送转记录（235 只股票）。BaoStock 也没有这些记录，多半是配股：回测时如果持有，会按复权因子推算，并在结果里写明。')
})
