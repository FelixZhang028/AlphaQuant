import assert from 'node:assert/strict'
import test from 'node:test'
import { researchContext, researchUrl, strategyReference } from '../src/workspace/researchNavigation.js'
import { allItems, groups, navigationItem, resolveView, views } from '../src/workspace/modules.js'

test('AI 投研三项入口，旧经验链接归入同一知识库且标签上下文可恢复', () => {
  const group = groups.find((g) => g.label === 'AI 智能投研')
  assert.deepEqual(group.items.map((item) => item.label), ['AI研究员', '投研知识库', '决策辅助'])
  assert.equal(navigationItem('prior-knowledge').key, 'knowledge-base')
  assert.ok(allItems.some((item) => item.key === 'prior-knowledge'))
  assert.equal(views['prior-knowledge'], views['knowledge-base'])
  const url = researchUrl('http://localhost/app.html?view=prior-knowledge', { view: 'knowledge-base', mode: 'experience' })
  assert.equal(researchContext(url).mode, 'experience')
  assert.equal(researchContext(researchUrl(url, 'decision-center')).mode, '')
})

test('策略研究五个主入口与两项回测步骤，旧链接仍然可达', () => {
  const group = groups.find((g) => g.label === '策略研究')
  assert.deepEqual(group.items.map((i) => i.label), ['行情图表', '我的策略', '因子研究', '回测与验证', '研究记录'])
  assert.deepEqual(group.items[3].children.map((i) => i.label), ['策略回测', '参数验证'])
  for (const key of ['strategy-studio', 'custom-strategy', 'nl-strategy']) {
    assert.ok(allItems.some((i) => i.key === key))
    assert.equal(navigationItem(key).key, 'strategy-hub')
  }
  // 参数优化与样本外验证合并为一页：旧的样本外验证链接落到同一页，其他链接不受影响。
  assert.equal(resolveView('walk-forward'), 'research')
  assert.ok(views[resolveView('walk-forward')])
  assert.equal(resolveView('factor-lab'), 'factor-lab')
})
test('保存策略引用保持类型与身份，名称不参与匹配', () => {
  assert.equal(strategyReference({ package_id: 'abc', name: '重名' }), 'package:abc')
  assert.equal(strategyReference({ plugin_name: 'abc', display_name: '重名' }), 'user:abc')
})
test('带策略和历史记录的链接刷新后仍能恢复，普通导航清除旧上下文', () => {
  const url = researchUrl('http://localhost/app.html?view=overview&theme=dark&run=9', {
    view: 'backtest-review', strategy: 'package:alpha', run: 12, mode: 'reuse', ignored: 'value',
  })
  assert.deepEqual(researchContext(url), { strategy: 'package:alpha', run: '12', baseline: '', mode: 'reuse', symbol: '' })
  assert.equal(url.searchParams.get('ignored'), null)
  assert.equal(url.searchParams.get('theme'), 'dark')
  assert.deepEqual(researchContext(researchUrl(url, 'factor-lab')), { strategy: '', run: '', baseline: '', mode: '', symbol: '' })
})
test('行情图表的股票代码写入链接，离开该页后清除', () => {
  const url = researchUrl('http://localhost/app.html?view=data-management', { view: 'market-chart', symbol: '000001' })
  assert.equal(url.searchParams.get('view'), 'market-chart')
  assert.equal(researchContext(url).symbol, '000001')
  assert.equal(navigationItem('market-chart').label, '行情图表')
  assert.ok(views['market-chart'])
  assert.equal(researchContext(researchUrl(url, 'strategy-hub')).symbol, '')
})
