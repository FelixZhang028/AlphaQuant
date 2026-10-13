import assert from 'node:assert/strict'
import test from 'node:test'
import { factorsBySource, filterFactors, filterOptions } from '../src/workspace/factorFilters.js'

const factors = [
  { name: 'alpha101_006', source: 'Alpha101', logical_category: 'K线与量价关系' },
  { name: 'alpha101_009', source: 'Alpha101', logical_category: '动量与趋势' },
  { name: 'momentum_20', source: '内置', logical_category: '动量与趋势' },
  { name: 'volatility_20', source: '内置', logical_category: '波动与风险' },
  { name: 'my_factor', source: '自定义', logical_category: '动量与趋势' },
]
const names = (list) => list.map((factor) => factor.name)
const counts = (options) => options.map((option) => `${option.label}:${option.count}`)

test('不筛选时列出全部；来源和类型可以单独或同时筛选', () => {
  assert.deepEqual(names(filterFactors(factors, { source: '', type: '' })), names(factors))
  assert.deepEqual(names(filterFactors(factors, { source: 'Alpha101', type: '' })), ['alpha101_006', 'alpha101_009'])
  assert.deepEqual(names(filterFactors(factors, { source: '', type: '动量与趋势' })), ['alpha101_009', 'momentum_20', 'my_factor'])
  assert.deepEqual(names(filterFactors(factors, { source: '内置', type: '动量与趋势' })), ['momentum_20'])
  assert.deepEqual(filterFactors(factors, { source: '自定义', type: '波动与风险' }), [])
})

test('已经选中的因子即使不符合筛选条件也保留', () => {
  assert.deepEqual(names(filterFactors(factors, { source: '内置', type: '' }, ['alpha101_006'])), ['alpha101_006', 'momentum_20', 'volatility_20'])
})

test('筛选项来自因子自己的字段，常见的排在前面，数量按另一排的选择计算', () => {
  const all = filterOptions(factors, { source: '', type: '' })
  assert.deepEqual(counts(all.source), ['全部:5', '内置:2', 'Alpha101:2', '自定义:1'])
  assert.deepEqual(counts(all.type), ['全部:5', '动量与趋势:3', '波动与风险:1', 'K线与量价关系:1'])
  const alpha = filterOptions(factors, { source: 'Alpha101', type: '动量与趋势' })
  assert.deepEqual(counts(alpha.type), ['全部:2', '动量与趋势:1', '波动与风险:0', 'K线与量价关系:1'])
  assert.deepEqual(counts(alpha.source), ['全部:3', '内置:1', 'Alpha101:1', '自定义:1'])
})

test('新的来源和类型不用改代码就会出现在筛选项里，没有字段的归到“其他”和“未分类”', () => {
  const more = [...factors, { name: 'pe_ttm', source: '基本面', logical_category: '估值' }, { name: 'odd' }]
  const options = filterOptions(more, { source: '', type: '' })
  assert.deepEqual(options.source.map((option) => option.label).slice(-2), ['基本面', '其他'])
  assert.deepEqual(options.type.map((option) => option.label).slice(-2), ['估值', '未分类'])
  assert.deepEqual(names(filterFactors(more, { source: '基本面', type: '估值' })), ['pe_ttm'])
})

test('下拉框按来源分组，内置在前', () => {
  assert.deepEqual(factorsBySource(factors).map((group) => [group.label, names(group.factors)]), [
    ['内置', ['momentum_20', 'volatility_20']], ['Alpha101', ['alpha101_006', 'alpha101_009']], ['自定义', ['my_factor']],
  ])
})
