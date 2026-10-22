import assert from 'node:assert/strict'
import test from 'node:test'
import { researchContext, researchUrl, strategyReference } from '../src/workspace/researchNavigation.js'
import { allItems, groups, navigationItem, resolveView, views } from '../src/workspace/modules.js'

test('市场研究：AI研究员、条件选股、事件研究、行情图表；文档问答、决策辅助的旧链接仍能打开，旧的研究经验链接进入 AI研究员', () => {
  const group = groups.find((g) => g.label === '市场研究')
  assert.deepEqual(group.items.map((item) => item.label), ['AI研究员', '条件选股', '事件研究', '行情图表'])
  assert.ok(views['event-study'] && views['stock-screen'])
  for (const key of ['knowledge-base', 'decision-center']) {
    assert.ok(allItems.some((item) => item.key === key))
    assert.ok(views[key])
    assert.equal(navigationItem(key).key, 'agent-lab')
  }
  assert.equal(resolveView('prior-knowledge'), 'agent-lab')
  const url = researchUrl('http://localhost/app.html?view=knowledge-base', { view: 'knowledge-base', mode: 'documents' })
  assert.equal(researchContext(url).mode, 'documents')
  assert.equal(researchContext(researchUrl(url, 'decision-center')).mode, '')
})

test('策略研究四个主入口与两项回测步骤，旧链接仍然可达', () => {
  const group = groups.find((g) => g.label === '策略研究')
  assert.deepEqual(group.items.map((i) => i.label), ['我的策略', '因子研究', '回测与验证', '研究记录'])
  assert.deepEqual(group.items[2].children.map((i) => i.label), ['策略回测', '参数验证'])
  assert.ok(allItems.some((i) => i.key === 'strategy-studio'))
  assert.equal(navigationItem('strategy-studio').key, 'strategy-hub')
  // Python 策略已停用：页面不在了，旧链接落到我的策略。
  assert.ok(!allItems.some((i) => i.key === 'custom-strategy') && !views['custom-strategy'])
  assert.equal(resolveView('custom-strategy'), 'strategy-hub')
  // 三种创建方式合并为一页：旧的“自然语言创建”链接落到同一页。
  assert.equal(resolveView('nl-strategy'), 'strategy-studio')
  assert.ok(!allItems.some((i) => i.key === 'nl-strategy'))
  // 参数优化与样本外验证合并为一页：旧的样本外验证链接落到同一页，其他链接不受影响。
  assert.equal(resolveView('walk-forward'), 'research')
  assert.ok(views[resolveView('walk-forward')])
  assert.equal(resolveView('factor-lab'), 'factor-lab')
})
test('保存策略引用保持类型与身份，名称不参与匹配', () => {
  assert.equal(strategyReference({ package_id: 'abc', name: '重名' }), 'package:abc')
})
test('带策略和历史记录的链接刷新后仍能恢复，普通导航清除旧上下文', () => {
  const url = researchUrl('http://localhost/app.html?view=overview&theme=dark&run=9', {
    view: 'backtest-review', strategy: 'package:alpha', run: 12, mode: 'reuse', ignored: 'value',
  })
  assert.deepEqual(researchContext(url), { strategy: 'package:alpha', run: '12', baseline: '', mode: 'reuse', symbol: '', brief: '', preset: '' })
  assert.equal(url.searchParams.get('ignored'), null)
  assert.equal(url.searchParams.get('theme'), 'dark')
  assert.deepEqual(researchContext(researchUrl(url, 'factor-lab')), { strategy: '', run: '', baseline: '', mode: '', symbol: '', brief: '', preset: '' })
})
test('行情图表的股票代码写入链接，离开该页后清除', () => {
  const url = researchUrl('http://localhost/app.html?view=data-management', { view: 'market-chart', symbol: '000001' })
  assert.equal(url.searchParams.get('view'), 'market-chart')
  assert.equal(researchContext(url).symbol, '000001')
  assert.equal(navigationItem('market-chart').label, '行情图表')
  assert.ok(views['market-chart'])
  assert.equal(researchContext(researchUrl(url, 'strategy-hub')).symbol, '')
})
