import assert from 'node:assert/strict'
import test from 'node:test'
import { evidenceText, factGroups, modelText, remainingText, tiltTone } from '../src/workspace/aiPresentation.js'
import { researchContext, researchUrl } from '../src/workspace/researchNavigation.js'

test('数据按组排列，保持后端给的顺序', () => {
  const facts = [
    { key: 'close', group: '价格走势' }, { key: 'ret_5d', group: '价格走势' }, { key: 'pe_ttm', group: '估值' },
  ]
  assert.deepEqual(factGroups(facts).map((g) => [g.group, g.items.map((f) => f.key)]), [['价格走势', ['close', 'ret_5d']], ['估值', ['pe_ttm']]])
  assert.deepEqual(factGroups(), [])
})

test('没有模型、次数和管理员的说明', () => {
  assert.equal(modelText({ ai: { available: false } }), '平台还没有配置 AI 模型：分析时只显示数据，不会有 AI 解读。')
  assert.equal(modelText({ ai: { available: true, model: 'deepseek-v4-pro' }, usage: { brief: { limit: 5, used: 1, remaining: 4 } } }),
    'AI 模型 deepseek-v4-pro · 今天还可以分析 4 次')
  assert.equal(modelText({ ai: { available: true, model: 'm' }, usage: { brief: { limit: null, used: 9, remaining: null } } }), 'AI 模型 m')
  assert.equal(remainingText({ remaining: 0 }, '追问'), '今天的追问次数已用完')
})

test('依据只在日期不同时写日期，倾向有各自的颜色', () => {
  assert.equal(evidenceText({ label: '市盈率', text: '19.6', as_of: '2026-10-13' }, '2026-10-13'), '市盈率：19.6')
  assert.equal(evidenceText({ label: '最新财报', text: '半年报', as_of: '2026-08-20' }, '2026-10-13'), '最新财报：半年报（2026-08-20）')
  assert.notEqual(tiltTone('偏多'), tiltTone('偏空'))
  assert.equal(tiltTone('中性'), tiltTone('其他'))
})

test('分析编号写进链接，刷新后能打开同一次分析', () => {
  const url = researchUrl('http://localhost/app.html?view=agent-lab', { view: 'agent-lab', brief: 'abc123' })
  assert.equal(researchContext(url).brief, 'abc123')
  assert.equal(researchContext(researchUrl(url, 'data-update')).brief, '')
})
