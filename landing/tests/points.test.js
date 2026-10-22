import assert from 'node:assert/strict'
import test from 'node:test'
import { cardText, checkinCells, checkinText, chinaDate, cleanCode, codeProblem, expiresSoon, expiryText, ledgerText, monthDay, priceText, signed } from '../src/workspace/points.js'

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

test('每日打卡的说法', () => {
  const base = { enabled: true, days: 30, ladder: [5, 7, 9, 11, 13, 15, 15], card_every: 7 }
  assert.equal(checkinText({ ...base, done_today: false, streak: 0, today_points: 5 }), '今天打卡可得 5 积分')
  assert.equal(checkinText({ ...base, done_today: false, streak: 2, today_points: 9 }), '已连续 2 天，今天打卡可得 9 积分')
  assert.equal(checkinText({ ...base, done_today: true, streak: 3, next_points: 11 }), '已连续 3 天，明天打卡可得 11 积分')
  assert.equal(checkinText({ ...base, enabled: false }), '')
  assert.equal(checkinText(null), '')
  assert.equal(cardText({ ...base, cards: 1, card_in: 3 }), '补签卡 1 张 · 再打卡 3 天送 1 张')
  assert.equal(cardText({ ...base, card_every: 0 }), '')
  assert.equal(monthDay('2026-10-20'), '10 月 20 日')
})

test('连续打卡的 7 格', () => {
  const ladder = [5, 7, 9, 11, 13, 15, 15]
  const status = (state) => checkinCells({ ladder, ...state }).map((c) => c.status[0]).join('')
  assert.equal(status({ streak: 0, done_today: false }), 'tllllll')
  assert.equal(status({ streak: 2, done_today: false }), 'ddtllll')
  assert.equal(status({ streak: 3, done_today: true }), 'dddllll')
  assert.equal(status({ streak: 9, done_today: false }), 'ddddddt')     // 第 10 天：还是按第 7 格
  assert.equal(status({ streak: 10, done_today: true }), 'ddddddd')
  assert.equal(checkinCells({ ladder, streak: 0, done_today: false })[6].label, '第 7 天起')
  assert.equal(checkinCells({ ladder, streak: 0, done_today: false })[6].short, '7 天+')
})
