import assert from 'node:assert/strict'
import test from 'node:test'
import { candidateGrid, candidateLabel, combinationCount, parameterHint, parseCandidates } from '../src/workspace/researchGrid.js'

test('候选值支持中英文逗号，去掉空白和重复', () => {
  assert.deepEqual(parseCandidates(' 10, 20，30 ,20,'), [10, 20, 30])
  assert.deepEqual(parseCandidates('0.0，0.05'), [0, 0.05])
  assert.deepEqual(parseCandidates('true,false'), ['true', 'false'])
  assert.deepEqual(parseCandidates(''), [])
  assert.deepEqual(parseCandidates(null), [])
})

test('没有选参数或没有候选值的行不进入网格，组合数是各参数取值个数的乘积', () => {
  const grid = candidateGrid([{ name: 'short_window', values: '10,20,30' }, { name: 'long_window', values: '60,120' },
    { name: '', values: '1,2' }, { name: 'unused', values: ' ' }])
  assert.deepEqual(grid, { short_window: [10, 20, 30], long_window: [60, 120] })
  assert.equal(combinationCount(grid), 6)
  assert.equal(combinationCount({}), 0)
})

test('参数提示写出基准取值和允许范围', () => {
  assert.equal(parameterHint({ current: 20, kind: 'integer', minimum: 2, maximum: 250, choices: [] }), '基准中的取值 20，允许范围 2 ~ 250')
  assert.equal(parameterHint({ current: 0, kind: 'number', minimum: 0, maximum: null, choices: [] }), '基准中的取值 0，允许范围 0 ~ 不限')
  assert.equal(parameterHint({ current: 'mock', kind: 'string', choices: ['mock', 'kimi'] }), '基准中的取值 mock，可选 mock / kimi')
  assert.equal(parameterHint({ current: true, kind: 'boolean', choices: [] }), '基准中的取值 true，可填 true / false')
  assert.equal(parameterHint(undefined), '')
  assert.equal(parameterHint({ current: 20, kind: 'integer', minimum: 2, maximum: 250, choices: [], description: '用于动量排名的交易日数量' }),
    '基准中的取值 20，允许范围 2 ~ 250，用于动量排名的交易日数量')
})

test('调仓频率的英文取值带中文说明，结果里直接显示中文', () => {
  const rebalance = { current: 'weekly', kind: 'string', choices: ['daily', 'weekly', 'monthly'],
    choice_labels: { daily: '每日', weekly: '每周', monthly: '每月' }, description: 'daily 表示每日' }
  assert.equal(parameterHint(rebalance), '基准中的取值 weekly（每周），可选 daily（每日） / weekly（每周） / monthly（每月）')
  assert.equal(candidateLabel(rebalance, 'monthly'), '每月')
  assert.equal(candidateLabel({ choice_labels: {} }, 5), 5)
  assert.equal(candidateLabel(undefined, 5), 5)
})
