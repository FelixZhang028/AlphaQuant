import assert from 'node:assert/strict'
import test from 'node:test'
import { factorGroups, selectedInGroup } from '../src/workspace/factorGroups.js'

const factors = [
  { name: 'momentum_20', source: '内置' },
  { name: 'alpha101_006', source: 'Alpha101' },
  { name: 'my_factor', source: '自定义' },
  { name: 'alpha101_041', source: 'Alpha101' },
]
const names = (group) => group.factors.map((factor) => factor.name)

test('常用因子一组，Alpha101 另成一组并默认折叠', () => {
  const [common, alpha] = factorGroups(factors)
  assert.deepEqual([common.key, common.folded, names(common)], ['common', false, ['momentum_20', 'my_factor']])
  assert.deepEqual([alpha.key, alpha.folded, names(alpha)], ['alpha101', true, ['alpha101_006', 'alpha101_041']])
  assert.match(alpha.title, /Alpha101.*学习/)
  assert.ok(alpha.note.includes('因子评估'))
})

test('没有 Alpha101 因子时只有常用这一组', () => {
  assert.deepEqual(factorGroups([factors[0]]).map((group) => group.key), ['common'])
  assert.deepEqual(factorGroups([]).map((group) => [group.key, group.factors.length]), [['common', 0]])
})

test('折叠的组在标题上提示已选了几个', () => {
  const [common, alpha] = factorGroups(factors)
  assert.equal(selectedInGroup(alpha, ['alpha101_041', 'momentum_20', '']), 1)
  assert.equal(selectedInGroup(common, ['alpha101_041', 'momentum_20']), 1)
  assert.equal(selectedInGroup(alpha, []), 0)
})
