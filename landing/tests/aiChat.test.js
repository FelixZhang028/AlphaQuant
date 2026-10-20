import test from 'node:test'
import assert from 'node:assert/strict'
import { blockLinks, chatContext, codeColumn, dataSummary, focusText, suggestionsFor, usageText } from '../src/workspace/aiChat.js'

test('推荐问题：看着一只股票或一次回测时换成和它有关的问题，否则按页面推荐', () => {
  assert.match(suggestionsFor('market-lookup', { symbol: '600519', name: '贵州茅台' })[0], /^贵州茅台最近四个季度/)
  assert.match(suggestionsFor('backtest-review', { backtest: 3 })[0], /这次回测的最大回撤/)
  assert.equal(suggestionsFor('factor-lab', null)[0], '动量类因子有哪些？')
  assert.equal(suggestionsFor('没有这个页面', null).length, 3)
})

test('正在看的内容：显示的说法和发给后端的内容；用户可以不带上', () => {
  const focus = { symbol: '600519', name: '贵州茅台' }
  assert.equal(focusText(focus), '贵州茅台（600519）')
  assert.equal(focusText({ backtest: 7 }), '第 7 号回测')
  assert.equal(focusText(null), '')
  assert.deepEqual(chatContext('股票查询', focus), { page: '股票查询', symbol: '600519' })
  assert.deepEqual(chatContext('股票查询', focus, false), { page: '股票查询' })
  assert.deepEqual(chatContext('策略回测', { backtest: 7 }), { page: '策略回测', backtest: '7' })
  assert.deepEqual(chatContext('', null), {})
})

test('数据表里的代码可以点；数据块下面的跳转', () => {
  assert.equal(codeColumn({ columns: ['排名', '股票', '代码'] }), 2)
  assert.equal(codeColumn({ columns: ['项目', '数值'] }), -1)
  const stock = blockLinks({ kind: 'stock', symbols: ['600519'] })
  assert.deepEqual(stock.map((link) => link.view), ['market-lookup', 'agent-lab'])
  assert.deepEqual(blockLinks({ kind: 'financials', symbols: ['600519'] })[0].context, { symbol: '600519', mode: 'financials' })
  assert.deepEqual(blockLinks({ kind: 'backtest', backtest: 3 }), [{ label: '打开这次回测', view: 'backtest-review', context: { run: 3 } }])
  assert.deepEqual(blockLinks({ kind: 'stock', error: '没有找到' }), [])
  assert.equal(dataSummary({ data: [{ title: 'a' }, { title: 'b', error: 'x' }] }), '用到的数据（1 项，1 项没有查到）')
  assert.equal(dataSummary({ data: [{ title: 'a' }] }), '用到的数据（1 项）')
  assert.equal(dataSummary({ data: [{ title: 'b', error: 'x' }] }), '查过的数据（1 项没有查到）')
})

test('次数的说法', () => {
  assert.equal(usageText({ limit: 20, used: 2, remaining: 18 }), '今天还能问 18 次（每天 20 次）')
  assert.equal(usageText({ limit: 20, used: 20, remaining: 0 }), '今天的 20 次已经用完，明天再来')
  assert.equal(usageText({ limit: null, used: 5, remaining: null }), '管理员不限次数')
  assert.equal(usageText(null), '')
})
