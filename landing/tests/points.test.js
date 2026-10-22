import assert from 'node:assert/strict'
import test from 'node:test'
import { chinaDate, cleanCode, codeProblem, expiresSoon, expiryText, ledgerText, priceText, signed } from '../src/workspace/points.js'

test('到期时间按北京时间写日期，快到期的提醒', () => {
  assert.equal(chinaDate('2026-11-20T17:00:00+00:00'), '2026-11-21')
  assert.equal(chinaDate(''), '')
  const now = new Date('2026-10-22T00:00:00Z')
  assert.equal(expiryText('2026-11-21T00:00:00Z', now), '2026-11-21 到期（还有 30 天）')
  assert.equal(expiryText('2026-10-22T05:00:00Z', now), '2026-10-22 到期（今天）')
  assert.equal(expiresSoon('2026-10-25T00:00:00Z', now), true)
  assert.equal(expiresSoon('2026-11-21T00:00:00Z', now), false)
})

test('明细和价格的说法', () => {
  assert.equal(signed(100), '+100')
  assert.equal(signed(-3), '-3')
  assert.equal(ledgerText({ kind: 'signup', label: '注册赠送', feature: '', note: '欢迎使用镜思 Prismind' }), '注册赠送 · 欢迎使用镜思 Prismind')
  assert.equal(ledgerText({ kind: 'spend', label: '使用', feature: 'AI 解读', note: '' }), 'AI 解读')
  assert.equal(priceText({ free_per_day: 3, free_left: 2, cost: 3 }), '每天免费 3 次（今天还剩 2 次），之后每次 3 积分')
  assert.equal(priceText({ free_per_day: 0, free_left: 0, cost: 1 }), '每次 1 积分')
  assert.equal(priceText({ free_per_day: 3, free_left: 2, cost: 3 }, true), '管理员不限次数，不扣积分')
})

test('兑换码去掉空格、换成大写，格式不对先提示', () => {
  assert.equal(cleanCode(' pm-abcd efgh '), 'PM-ABCDEFGH')
  assert.equal(codeProblem(''), '请输入兑换码')
  assert.equal(codeProblem('兑换码'), '兑换码只包含字母、数字和短横线')
  assert.equal(codeProblem('PM-ABCD-EFGH-JKLM'), '')
})
