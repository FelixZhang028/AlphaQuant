import test from 'node:test'
import assert from 'node:assert/strict'
import { ASPECTS, FACTORS, aspectSummary, aspectsFrom, factorRow, level } from '../src/workspace/factorProfile.js'

// 截图里那只股票当天的因子（真实数据）。
const row = (name, value, market, industry) => ({ name, display_name: name, value, market_share: market, industry_share: industry })
const items = [
  row('momentum_20', -0.176108, 0.0957, 0.1051), row('reversal_5', 0.044953, 0.9445, 0.952), row('volatility_20', 0.048061, 0.9256, 0.9369),
  row('amount_change_20', -0.235871, 0.3062, 0.3554), row('rsi_14', 40.43, 0.4288, 0.5225), row('high_distance_20', -0.318009, 0.0372, 0.03),
  row('volume_ratio_5', 0.936912, 0.493, 0.5572), row('pv_corr_20', 0.524415, 0.5697, 0.5572), row('bias_10', 0.037499, 0.9364, 0.9399),
  row('amplitude_20', 0.054416, 0.7843, 0.8198), row('ep_ttm', 0.0326, 0.7112, 0.7387), row('bp_mrq', 0.262467, 0.3001, 0.2913),
  row('sp_ttm', 0.598265, 0.7209, 0.6366), row('cfp_ttm', -0.007035, 0.4001, 0.4174), row('roe_ttm', 0.124207, 0.8675, 0.845),
  row('net_margin_ttm', 0.054491, 0.5761, 0.6817), row('gross_margin', 0.167677, 0.3061, 0.3934), row('debt_ratio', 0.523851, 0.6671, 0.5897),
  row('yoy_net_profit', 0.88753, 0.8269, 0.8649), row('yoy_equity', 0.126667, 0.8391, 0.8048), row('ln_market_cap', 25.578611, 0.9761, 0.982),
  row('turnover_20', 6.20806, 0.901, 0.8946), row('turnover_change_20', -0.063086, 0.496, 0.5572),
]

test('每个内置因子都有通俗名字、解释，并且归到一个方面里', () => {
  const grouped = ASPECTS.flatMap((a) => a.factors)
  assert.equal(new Set(grouped).size, grouped.length)                    // 一个因子只在一个方面
  for (const item of items) {
    assert.ok(FACTORS[item.name]?.label && FACTORS[item.name].what, item.name)
    assert.ok(grouped.includes(item.name), item.name)
  }
  assert.deepEqual([0.05, 0.2, 0.5, 0.75, 0.95, null].map(level), [0, 1, 2, 3, 4, null])
})

test('七个方面各一句话：只描述这只股票现在的样子', () => {
  const aspects = aspectsFrom(items)
  const said = Object.fromEntries(aspects.map((a) => [a.key, [a.text, a.basis]]))
  assert.deepEqual(aspects.map((a) => a.title), ['近期走势', '波动大小', '交易热度', '估值', '赚钱能力', '成长', '公司规模'])
  assert.deepEqual(said.trend, ['近一个月比大多数股票弱，最近 5 天明显强于大多数股票', '近 20 天 -17.6%，近 5 天 +4.5%'])
  assert.deepEqual(said.volatility, ['偏大', '每天涨跌的幅度比 93% 的股票大'])
  assert.deepEqual(said.heat, ['很活跃', '每天换手率 6.21%，比 90% 的股票高'])
  assert.deepEqual(said.value, ['按利润看偏便宜，按净资产看不贵也不便宜', '市盈率 30.7 倍，市净率 3.81 倍（和全市场比）'])
  assert.deepEqual(said.quality, ['偏强', '净资产收益率 12.4%，比 87% 的公司高'])
  assert.deepEqual(said.growth, ['利润增长偏快', '净利润同比 +88.8%，净资产同比 +12.7%'])
  assert.equal(said.size[0], '很大')
  assert.ok(aspectSummary(aspects).startsWith('近期走势：近一个月比大多数股票弱'))
  // 不出现“正向 / 反向”和买卖的说法
  assert.ok(!/正向|反向|买入|卖出|持有/.test(JSON.stringify(aspects)))
})

test('每一项：真实数值、五档位置、全市场和同行业里的说法', () => {
  const vol = factorRow(items[2])
  assert.equal(vol.label, '每天涨跌的幅度（波动率）')
  assert.equal(vol.value, '约 4.8%')
  assert.equal(vol.levelWord, '很高')
  assert.equal(vol.marketText, '全市场比 93% 的股票波动大')
  assert.equal(vol.industryText, '同行业里比 94% 的股票波动大')
  const pe = factorRow(items[10])
  assert.deepEqual([pe.value, pe.levelWord, pe.ends], ['30.7 倍', '偏便宜', ['贵', '便宜']])
  // 现金流为负：没法比贵还是便宜，不画位置
  const cash = factorRow(items[13])
  assert.deepEqual([cash.value, cash.levelWord, cash.market, cash.level], ['现金流为负', '没法比', null, null])
  assert.equal(factorRow(items[20]).value, '约 1,284 亿')
  assert.equal(factorRow({ name: 'new_one', display_name: '新因子', value: 1.23456, market_share: 0.5 }).label, '新因子')
})

test('亏损、利润下降、数据不全的写法', () => {
  const loss = aspectsFrom([row('ep_ttm', -0.01, 0.05, 0.1), row('bp_mrq', 0.9, 0.95, 0.9), row('roe_ttm', -0.05, 0.04, 0.1),
    row('yoy_net_profit', -0.32, 0.1, 0.2)])
  const said = Object.fromEntries(loss.map((a) => [a.key, a.text]))
  assert.equal(said.value, '公司亏损，没法按利润估值；按净资产看很便宜')
  assert.equal(said.quality, '亏损')
  assert.equal(said.growth, '利润比去年同期少了 32%')
  assert.deepEqual(aspectsFrom([]), [])
  assert.equal(aspectSummary([]), '')
  const other = aspectsFrom([row('mystery', 1, 0.5, null)])
  assert.deepEqual(other.map((a) => a.key), ['other'])
})
