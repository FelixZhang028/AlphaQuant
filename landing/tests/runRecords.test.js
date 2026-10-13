import assert from 'node:assert/strict'
import test from 'node:test'
import { backtestId, recordsSummary, runTime, strategyName, toggleSelection, validityLabel } from '../src/workspace/runRecords.js'

test('链接里的记录编号带不带 run- 前缀都能读出，无效写法不当成记录', () => {
  assert.equal(backtestId('run-12'), 12)
  assert.equal(backtestId('12'), 12)
  assert.equal(backtestId(12), 12)
  for (const value of ['', null, undefined, 'run-', 'abc', '0', '-3', '1.5']) assert.equal(backtestId(value), null)
})

test('对比最多勾选 5 条，再点一次取消勾选', () => {
  let selected = []
  for (const id of ['run-1', 'run-2', 'run-3', 'run-4', 'run-5']) selected = toggleSelection(selected, id)
  assert.equal(selected.length, 5)
  assert.equal(toggleSelection(selected, 'run-6'), null)
  assert.deepEqual(toggleSelection(selected, 'run-3'), ['run-1', 'run-2', 'run-4', 'run-5'])
})

test('运行时间显示成本地时间，到分钟；读不出时间时显示占位符', () => {
  assert.equal(runTime(new Date(2026, 9, 13, 9, 7, 18).toISOString()), '2026-10-13 09:07')
  for (const value of ['', null, undefined, 'not a date']) assert.equal(runTime(value), '—')
})

test('策略显示目录里的名称；策略已删除时显示记录里保存的名字', () => {
  const options = [{ value: 'a_share_momentum', label: 'A股动量策略' }, { value: 'user:mine', label: '我的策略 · Python' }]
  assert.equal(strategyName(options, 'a_share_momentum', 'a_share_momentum'), 'A股动量策略')
  assert.equal(strategyName(options, 'user:mine', 'user:mine'), '我的策略 · Python')
  assert.equal(strategyName(options, 'package:gone', '均线趋势'), '均线趋势')
  assert.equal(strategyName([], undefined, ''), '—')
})

test('数据状态显示中文，旧版记录单独说明', () => {
  assert.equal(validityLabel({ validity_status: 'VALID' }), '通过')
  assert.equal(validityLabel({ validity_status: 'WARNING' }), '需复核')
  assert.equal(validityLabel({ validity_status: 'INVALID' }), '不可用')
  assert.equal(validityLabel({ validity_status: 'VALID', legacy_unverified: true }), '旧版未验证')
  assert.equal(validityLabel({}), '待验证')
})

test('记录数量用一句话说明，没有旧版记录时不提', () => {
  assert.equal(recordsSummary(0, null), '还没有回测记录。')
  assert.equal(recordsSummary(3, { success: 2, failed: 1, legacy_unverified: 0 }), '共 3 条：成功 2，失败 1。')
  assert.equal(recordsSummary(4, { success: 3, failed: 0, legacy_unverified: 1 }), '共 4 条：成功 3，失败 0，旧版未验证 1。')
})
