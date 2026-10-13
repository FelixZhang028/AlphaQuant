import assert from 'node:assert/strict'
import test from 'node:test'
import { alpha101Count, visibleFactors } from '../src/workspace/factorVisibility.js'

const factors = [
  { name: 'momentum_20', source: '内置' },
  { name: 'alpha101_006', source: 'Alpha101' },
  { name: 'my_factor', source: '自定义' },
  { name: 'alpha101_041', source: 'Alpha101' },
]
const names = (list) => list.map((factor) => factor.name)

test('Alpha101 因子默认不列出，打开开关后排在常用因子后面', () => {
  assert.equal(alpha101Count(factors), 2)
  assert.deepEqual(names(visibleFactors(factors, false)), ['momentum_20', 'my_factor'])
  assert.deepEqual(names(visibleFactors(factors, true)), ['momentum_20', 'my_factor', 'alpha101_006', 'alpha101_041'])
})

test('已经选中的 Alpha101 因子在关着开关时仍然列出', () => {
  assert.deepEqual(names(visibleFactors(factors, false, ['alpha101_041', ''])), ['momentum_20', 'my_factor', 'alpha101_041'])
  assert.deepEqual(names(visibleFactors([], false, ['alpha101_041'])), [])
})
