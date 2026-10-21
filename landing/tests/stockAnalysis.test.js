import test from 'node:test'
import assert from 'node:assert/strict'
import { historyText, longAnalysis, shortAnalysis } from '../src/workspace/stockAnalysis.js'

const row = (name, value, market) => ({ name, display_name: name, value, market_share: market, industry_share: null })
const report = {
  factors: { items: [
    row('momentum_20', -0.176, 0.0957), row('reversal_5', 0.045, 0.9445), row('volatility_20', 0.048, 0.9256), row('amplitude_20', 0.054, 0.7843),
    row('turnover_20', 6.2, 0.901), row('volume_ratio_5', 0.94, 0.493), row('amount_change_20', -0.24, 0.3062),
    row('ep_ttm', 0.0326, 0.7112), row('bp_mrq', 0.2625, 0.3001), row('cfp_ttm', -0.007, 0.4),
    row('roe_ttm', 0.1242, 0.8675), row('debt_ratio', 0.52, 0.6671), row('yoy_net_profit', 0.8875, 0.8269), row('yoy_equity', 0.127, 0.8391),
  ] },
  checks: [
    { key: 'drawdown', state: 'warn', text: '距近一年最高价 -42.0%' }, { key: 'liquidity', state: 'ok', text: '近 20 日平均 12.3 亿元' },
    { key: 'profit_drop', state: 'ok', text: '净利润同比 +88.8%' },
  ],
  charts: { valuation: { start: '2023-10-09', bands: { pe_ttm: { current: 30.7, share: 0.86 }, pb_mrq: { current: 3.81, share: 0.5 } } } },
  financial_trend: { rows: [{ profit_yoy: 0.2, debt_ratio: 0.48 }, { profit_yoy: 0.5, debt_ratio: 0.5 }, { profit_yoy: 0.8875, debt_ratio: 0.52 }],
    trends: { profit_yoy: '连续上升', debt_ratio: '连续上升' } },
}
const study = {
  label: '近 20 个交易日跌了 18%',
  result: { events: 58325, main_horizon: 20, conditions: ['近 20 个交易日涨跌幅 ≤ -15%'],
    horizons: { 20: { events: { count: 57000, mean: 0.0386, up_share: 0.57 }, all: { mean: 0.0076 }, excess: { mean: 0.0072 } } } },
}
const FORBIDDEN = /买入|卖出|持有|加仓|减仓|目标价|看涨|看跌|建议/

test('短期分析：现在的状态、历史上类似的情况、要留意的', () => {
  const items = shortAnalysis(report, study)
  assert.deepEqual(items.map((i) => i.title), ['现在的状态', '历史上类似的情况', '要留意的'])
  assert.equal(items[0].text, '近一个月比大多数股票弱，最近 5 天明显强于大多数股票；波动偏大；交易很活跃。')
  assert.equal(items[1].text, '历史上全市场“近 20 个交易日涨跌幅 ≤ -15%”出现过 58,325 次；之后 20 个交易日平均 +3.9%（平时 +0.8%），上涨的占 57%；和同一天的全部股票比 +0.7%。')
  assert.equal(items[1].target, 'event-study')
  assert.equal(items[2].text, '距近一年最高价 -42.0%；波动大，短期上涨和下跌都可能很剧烈。')
  for (const item of items) assert.ok(!FORBIDDEN.test(item.text), item.text)
})

test('历史统计在算、算不出来、没有足够的次数', () => {
  assert.equal(historyText({ loading: true, label: 'x' }), '正在统计全市场历史上类似的情况……')
  assert.equal(historyText({ error: '超时', label: 'x' }), '没能统计历史上类似的情况：超时')
  assert.equal(historyText({ label: '当天涨停', result: { events: 0, main_horizon: 20, horizons: {} } }), '历史上全市场没有足够的“当天涨停”可以统计。')
  assert.deepEqual(shortAnalysis({ checks: [] }, null).map((i) => i.title), ['要留意的'])
  assert.equal(shortAnalysis({ checks: [] }, null)[0].text, '按短期的几条规则检查，没有发现需要特别留意的地方。')
})

test('长期分析：估值在自己历史里的位置、基本面、接下来要跟踪的数字', () => {
  const items = longAnalysis(report)
  assert.deepEqual(items.map((i) => i.title), ['估值', '基本面', '接下来要跟踪的'])
  assert.equal(items[0].text, '市盈率 30.7 倍，在它自己 2023 年以来的历史里处在偏高的位置（比 86% 的交易日高）；和全市场比：按利润看偏便宜，按净资产看不贵也不便宜。')
  assert.equal(items[0].target, 'report-valuation')
  assert.equal(items[1].text, '赚钱能力偏强；利润增长偏快；最近四份财报的利润增速连续上升；资产负债率连续上升。')
  assert.equal(items[2].text, '之后几份财报里值得看：净资产收益率能不能保持在 12% 左右；利润的高增长（+88.8%）能不能持续；资产负债率（52%）有没有继续上升。')
  for (const item of items) assert.ok(!FORBIDDEN.test(item.text), item.text)
})

test('亏损、利润下滑时的写法；没有数据时不硬写', () => {
  const loss = {
    factors: { items: [row('roe_ttm', -0.05, 0.04), row('yoy_net_profit', -0.32, 0.1), row('ep_ttm', -0.01, 0.05), row('bp_mrq', 0.9, 0.95)] },
    checks: [{ key: 'loss', state: 'warn', text: '最近四个季度合计亏损' }],
    charts: { valuation: { bands: { pb_mrq: { current: 1.1, share: 0.1 } } } },
  }
  const items = longAnalysis(loss)
  assert.equal(items[0].text, '市净率 1.10 倍，在它自己近几年的历史里处在偏低的位置（比 10% 的交易日高）；和全市场比：公司亏损，没法按利润估值；按净资产看很便宜。')
  assert.equal(items[1].text, '利润比去年同期少了 32%。需要留意：最近四个季度合计亏损。')
  // 没有“亏损”这条检查时，自己说一句
  assert.ok(longAnalysis({ ...loss, checks: [] })[1].text.startsWith('目前亏损；'))
  assert.equal(items[2].text, '之后几份财报里值得看：什么时候能扭亏为盈；利润下滑（-32.0%）有没有止住。')
  assert.deepEqual(longAnalysis({}), [])
})
