import assert from 'node:assert/strict'
import test from 'node:test'
import {
  evidenceText, factGroups, laterText, modelText, oddsDisagree, oddsText, overfitText, percent, pickSuggestion, remainingText, signedPercent, tiltLabel, tiltTone,
} from '../src/workspace/aiPresentation.js'
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
    'AI 模型 deepseek-v4-pro · 今天还可以免费分析 4 次')
  assert.equal(modelText({ ai: { available: true, model: 'm' }, usage: { brief: { limit: null, used: 9, remaining: null } } }), 'AI 模型 m')
  assert.equal(remainingText({ remaining: 0 }, '追问'), '今天的免费追问次数已用完')
  assert.equal(remainingText({ remaining: 0, cost: 1, points: 40 }, '追问'), '今天的免费追问次数已用完，再用每次 1 积分（现有 40）')
  assert.equal(remainingText({ remaining: 0, cost: 1, points: null }, '追问'), '今天的免费追问次数已用完')
})

test('依据只在日期不同时写日期，倾向换成对数据的说法，不用红绿色', () => {
  assert.equal(evidenceText({ label: '市盈率', text: '19.6', as_of: '2026-10-13' }, '2026-10-13'), '市盈率：19.6')
  assert.equal(evidenceText({ label: '最新财报', text: '半年报', as_of: '2026-08-20' }, '2026-10-13'), '最新财报：半年报（2026-08-20）')
  assert.deepEqual(['偏多', '中性', '偏空'].map(tiltLabel), ['利好多', '中性', '风险多'])
  assert.equal(tiltLabel(''), '')
  assert.equal(tiltTone('偏多'), tiltTone('偏空'))
  assert.notEqual(tiltTone('中性'), tiltTone('其他'))
})

test('分析编号写进链接，刷新后能打开同一次分析', () => {
  const url = researchUrl('http://localhost/app.html?view=agent-lab', { view: 'agent-lab', brief: 'abc123' })
  assert.equal(researchContext(url).brief, 'abc123')
  assert.equal(researchContext(researchUrl(url, 'data-update')).brief, '')
})

test('之后的走势和沪深300一起写出来', () => {
  const later = { end_date: '2026-10-13', days: 9, change: 0.032, benchmark: '沪深300', benchmark_change: -0.011 }
  assert.equal(laterText(later), '分析日之后到 2026-10-13（9 个交易日）：这只股票 +3.2%，同期沪深300 -1.1%。')
  assert.equal(laterText({ ...later, benchmark_change: null }), '分析日之后到 2026-10-13（9 个交易日）：这只股票 +3.2%。')
  assert.equal(laterText(null), '')
  assert.equal(signedPercent(0), '0.0%')
})

test('开始分析时用选过的股票、完整代码或列表里的第一只', () => {
  const list = [{ symbol: '600519', name: '贵州茅台' }, { symbol: '000858', name: '五粮液' }]
  assert.equal(pickSuggestion('600519 贵州茅台', { symbol: '600519', name: '贵州茅台' }, []), '600519')
  assert.equal(pickSuggestion(' 000001.sz ', null, list), '000001.sz')
  assert.equal(pickSuggestion('五粮液', null, list), '000858')
  assert.equal(pickSuggestion('茅台', null, list), '600519')
  assert.equal(pickSuggestion('不存在', null, []), '')
})

test('决策模型的概率：三种倾向都写出来，看法不同时能看出来', () => {
  const odds = { choice: '中性', probabilities: { 偏多: 0.25, 中性: 0.55, 偏空: 0.2 }, model: 'jev-1.13' }
  assert.equal(oddsText(odds), '决策模型 jev-1.13 的估计：利好多 25% · 中性 55% · 风险多 20%')
  assert.equal(oddsDisagree(odds, '偏多'), true)
  assert.equal(oddsDisagree(odds, '中性'), false)
  assert.equal(oddsText(null), '')
  assert.equal(percent(0.645), '65%')
})

test('过度拟合的可能分三档说明', () => {
  assert.match(overfitText(0.7), /很可能经不起/)
  assert.match(overfitText(0.5), /拿不准/)
  assert.match(overfitText(0.2), /不太像是巧合/)
})
