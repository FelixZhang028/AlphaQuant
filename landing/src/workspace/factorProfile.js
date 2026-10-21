// 因子画像怎么显示：把内置因子按“近期走势、波动、交易热度、估值、赚钱能力、成长、规模”七个方面归类，
// 每个方面先用一句话说清这只股票现在的样子，点开再看每一项的真实数值和在全市场、同行业里的位置。
// 只描述数据；“研究里的常见用法”只是背景知识，不是对这只股票的判断。

import { pct, signedPct, yi } from './researchReport.js'

const ok = (value) => typeof value === 'number' && Number.isFinite(value)
const fixed = (digits, unit = '') => (v) => (ok(v) ? `${v.toFixed(digits)}${unit}` : '—')
const inverse = (digits, bad) => (v) => (!ok(v) ? '—' : v > 0 ? `${(1 / v).toFixed(digits)} 倍` : bad)

// 五档位置：按“比多少比例的股票高”分。
export const LEVELS = ['很低', '偏低', '中等', '偏高', '很高']
export function level(share) {
  if (!ok(share)) return null
  return share >= 0.9 ? 4 : share >= 0.7 ? 3 : share > 0.3 ? 2 : share > 0.1 ? 1 : 0
}

// 每个因子：通俗名字、数值怎么写、“比别人高”在这里怎么说、是什么、研究里的常见用法。
// ends：位置条两头的说法（估值是“贵 / 便宜”）。
export const FACTORS = {
  momentum_20: { label: '近 20 个交易日涨跌幅', format: signedPct, higher: '涨得多',
    what: '过去 20 个交易日的涨跌幅。', rule: '研究里常见：近期涨得多的股票，之后一段时间往往还会强一些（趋势延续）。' },
  high_distance_20: { label: '离 20 日最高价', format: signedPct, higher: '更接近高点',
    what: '收盘价比过去 20 天的最高价低多少，0 表示正好在高点。', rule: '越接近高点，常被看作走势越强。' },
  reversal_5: { label: '近 5 个交易日涨跌幅', format: signedPct, higher: '涨得多',
    what: '过去 5 个交易日的涨跌幅。', rule: '研究里常见：短期涨得太多之后容易回落，跌得多之后容易反弹（短期反转）。' },
  bias_10: { label: '比 10 日均线高出', format: signedPct, higher: '高出均线更多',
    what: '收盘价比最近 10 天的平均价高出（负数是低出）多少。', rule: '偏离均线越远，之后越容易往均线回靠。' },
  rsi_14: { label: '短期强弱（RSI，0～100）', format: fixed(0), higher: '更强',
    what: '近 14 天上涨力量和下跌力量的对比。70 以上常被叫做“超买”，30 以下叫“超卖”。', rule: '数值很高时，常被看作短期涨得过头。' },
  volatility_20: { label: '每天涨跌的幅度（波动率）', format: (v) => (ok(v) ? `约 ${pct(v)}` : '—'), higher: '波动大',
    what: '过去 20 天每天涨跌幅的标准差，越大说明每天涨跌越剧烈。', rule: '研究里常见：波动小的股票，扣除风险以后表现通常更好。' },
  amplitude_20: { label: '每天最高最低价差（振幅）', format: (v) => (ok(v) ? `日均 ${pct(v)}` : '—'), higher: '振幅大',
    what: '过去 20 天每天最高价和最低价相差多少（占前一天收盘价的比例）的平均。', rule: '振幅小的股票走势通常更稳。' },
  turnover_20: { label: '每天换手率（20 日平均）', format: fixed(2, '%'), higher: '交易更活跃',
    what: '过去 20 天平均每天有多少比例的流通股被买卖。', rule: '研究里常见：交易太拥挤的股票，之后表现往往偏弱。' },
  turnover_change_20: { label: '近 5 日换手率比 20 日平均', format: signedPct, higher: '换手增加更多',
    what: '最近 5 天的平均换手率，比最近 20 天的平均多（负数是少）多少。', rule: '换手突然升温，常被看作交易变拥挤。' },
  amount_change_20: { label: '近 5 日成交额比 20 日平均', format: signedPct, higher: '放量更多',
    what: '最近 5 天的平均成交额，比最近 20 天的平均多（负数是少）多少。', rule: '成交额增加，常被看作关注度提高。' },
  volume_ratio_5: { label: '近 5 日成交量是 20 日平均的', format: fixed(2, ' 倍'), higher: '放量更多',
    what: '最近 5 天的平均成交量，是最近 20 天平均的几倍；大于 1 说明最近放量。', rule: '短期放量常被看作资金关注度提高。' },
  pv_corr_20: { label: '价格和成交量同步的程度', format: fixed(2), higher: '量价更同步',
    what: '过去 20 天价格和成交量是不是同涨同跌，-1 到 1，越接近 1 越同步。', rule: '量价走势背离（负数）时，常被看作可能转向的信号。' },
  ep_ttm: { label: '市盈率（按利润看）', format: inverse(1, '亏损'), higher: '便宜', ends: ['贵', '便宜'], cheap: true,
    what: '股价 ÷ 每股利润（过去 12 个月）。越低越便宜；亏损的公司没有可比的市盈率。', rule: '研究里常见：估值便宜的股票，长期看平均表现更好。' },
  bp_mrq: { label: '市净率（按净资产看）', format: inverse(2, '净资产为负'), higher: '便宜', ends: ['贵', '便宜'], cheap: true,
    what: '股价 ÷ 每股净资产。越低越便宜。', rule: '研究里常见：估值便宜的股票，长期看平均表现更好。' },
  sp_ttm: { label: '市销率（按营收看）', format: inverse(2, '—'), higher: '便宜', ends: ['贵', '便宜'], cheap: true,
    what: '股价 ÷ 每股营业收入（过去 12 个月）。越低越便宜。', rule: '研究里常见：估值便宜的股票，长期看平均表现更好。' },
  cfp_ttm: { label: '市现率（按现金流看）', format: inverse(1, '现金流为负'), higher: '便宜', ends: ['贵', '便宜'], cheap: true,
    what: '股价 ÷ 每股经营现金流（过去 12 个月）。越低越便宜；经营现金流为负时没有可比的市现率。', rule: '研究里常见：估值便宜的股票，长期看平均表现更好。' },
  roe_ttm: { label: '净资产收益率（赚钱能力）', format: pct, higher: '高',
    what: '过去 12 个月净利润 ÷ 净资产，也就是用股东的钱赚钱的能力。', rule: '越高说明赚钱能力越强。' },
  net_margin_ttm: { label: '净利率', format: pct, higher: '高',
    what: '每 100 元营业收入，最后剩下多少净利润（过去 12 个月）。', rule: '越高说明赚钱越不费力。' },
  gross_margin: { label: '毛利率', format: pct, higher: '高',
    what: '每 100 元营业收入，扣掉直接成本以后还剩多少（最新财报）。银行等行业没有这一项。', rule: '越高通常说明产品越有定价能力。' },
  debt_ratio: { label: '资产负债率', format: pct, higher: '高',
    what: '负债占总资产的比例（最新财报）。不同行业差别很大，银行天然很高。', rule: '负债越高，财务风险通常越大。' },
  yoy_net_profit: { label: '净利润同比增长', format: signedPct, higher: '增长快',
    what: '最新财报的净利润，比去年同期增长了多少。', rule: '越高说明利润增长越快。' },
  yoy_equity: { label: '净资产同比增长', format: signedPct, higher: '增长快',
    what: '最新财报的净资产，比去年同期增长了多少。', rule: '越高说明公司家底积累得越快。' },
  ln_market_cap: { label: '总市值', format: (v) => (ok(v) ? `约 ${yi(Math.exp(v))}` : '—'), higher: '大',
    what: '股价 × 总股本，也就是整个公司在股市上值多少钱。', rule: 'A 股历史上小市值股票平均收益更高，但波动也更大。' },
}

const find = (items, name) => items.find((item) => item.name === name)
const shareOf = (item) => (ok(item?.market_share) ? item.market_share : null)
const word = (share, words) => (ok(share) ? words[level(share)] : null)
const percent = (share) => `${Math.round(share * 100)}%`
const mean = (values) => { const known = values.filter(ok); return known.length ? known.reduce((a, b) => a + b, 0) / known.length : null }

// 七个方面：包含哪些因子，怎么用一句话说。headline 返回 { text, basis }，没有数据时返回 null。
export const ASPECTS = [
  {
    key: 'trend', title: '近期走势', factors: ['momentum_20', 'reversal_5', 'high_distance_20', 'bias_10', 'rsi_14'],
    headline(items) {
      const month = find(items, 'momentum_20')
      const week = find(items, 'reversal_5')
      const m = shareOf(month)
      const w = shareOf(week)
      if (!ok(m) && !ok(w)) return null
      const parts = []
      if (ok(m)) parts.push(m <= 0.2 ? '近一个月比大多数股票弱' : m >= 0.8 ? '近一个月比大多数股票强' : '近一个月和大多数股票差不多')
      if (ok(w) && w >= 0.8) parts.push('最近 5 天明显强于大多数股票')
      if (ok(w) && w <= 0.2) parts.push('最近 5 天明显弱于大多数股票')
      const basis = [ok(month?.value) && `近 20 天 ${signedPct(month.value)}`, ok(week?.value) && `近 5 天 ${signedPct(week.value)}`].filter(Boolean)
      return { text: parts.join('，'), basis: basis.join('，') }
    },
  },
  {
    key: 'volatility', title: '波动大小', factors: ['volatility_20', 'amplitude_20'],
    headline(items) {
      const vol = find(items, 'volatility_20')
      const share = mean([shareOf(vol), shareOf(find(items, 'amplitude_20'))])
      if (!ok(share)) return null
      return { text: word(share, ['很小', '偏小', '中等', '偏大', '很大']), basis: ok(shareOf(vol)) ? `每天涨跌的幅度比 ${percent(vol.market_share)} 的股票大` : '' }
    },
  },
  {
    key: 'heat', title: '交易热度', factors: ['turnover_20', 'turnover_change_20', 'amount_change_20', 'volume_ratio_5', 'pv_corr_20'],
    headline(items) {
      const turnover = find(items, 'turnover_20')
      const share = shareOf(turnover)
      if (!ok(share)) return null
      const recent = mean([shareOf(find(items, 'volume_ratio_5')), shareOf(find(items, 'amount_change_20'))])
      let text = word(share, ['很冷清', '偏冷清', '一般', '偏活跃', '很活跃'])
      if (ok(recent) && recent >= 0.8) text += '，最近明显放量'
      if (ok(recent) && recent <= 0.2) text += '，最近成交明显缩小'
      return { text, basis: `每天换手率 ${FACTORS.turnover_20.format(turnover.value)}，比 ${percent(share)} 的股票高` }
    },
  },
  {
    key: 'value', title: '估值', factors: ['ep_ttm', 'bp_mrq', 'sp_ttm', 'cfp_ttm'],
    headline(items) {
      const ep = find(items, 'ep_ttm')
      const bp = find(items, 'bp_mrq')
      const cheap = (item) => (!item || !ok(item.value) || !ok(item.market_share) ? null
        : item.value <= 0 ? '亏损' : ['很贵', '偏贵', '不贵也不便宜', '偏便宜', '很便宜'][level(item.market_share)])
      const e = cheap(ep)
      const b = cheap(bp)
      if (!e && !b) return null
      let text
      if (e === '亏损') text = `公司亏损，没法按利润估值${b ? `；按净资产看${b}` : ''}`
      else if (e && b) text = e === b ? `按利润和净资产看都${e}` : `按利润看${e}，按净资产看${b}`
      else text = e ? `按利润看${e}` : `按净资产看${b}`
      const basis = [ep && `市盈率 ${FACTORS.ep_ttm.format(ep.value)}`, bp && `市净率 ${FACTORS.bp_mrq.format(bp.value)}`].filter(Boolean).join('，')
      return { text, basis: `${basis}（和全市场比）` }
    },
  },
  {
    key: 'quality', title: '赚钱能力', factors: ['roe_ttm', 'net_margin_ttm', 'gross_margin', 'debt_ratio'],
    headline(items) {
      const roe = find(items, 'roe_ttm')
      if (!ok(shareOf(roe)) || !ok(roe.value)) return null
      let text = roe.value <= 0 ? '亏损' : word(roe.market_share, ['很弱', '偏弱', '中等', '偏强', '很强'])
      const debt = shareOf(find(items, 'debt_ratio'))
      if (ok(debt) && debt >= 0.9) text += '，负债率很高'
      else if (ok(debt) && debt >= 0.8) text += '，负债率偏高'
      return { text, basis: `净资产收益率 ${pct(roe.value)}，比 ${percent(roe.market_share)} 的公司高` }
    },
  },
  {
    key: 'growth', title: '成长', factors: ['yoy_net_profit', 'yoy_equity'],
    headline(items) {
      const profit = find(items, 'yoy_net_profit')
      const equity = find(items, 'yoy_equity')
      if (!ok(shareOf(profit)) || !ok(profit.value)) return null
      const text = profit.value < 0 ? `利润比去年同期少了 ${pct(-profit.value, 0)}`
        : `利润增长${word(profit.market_share, ['很慢', '偏慢', '速度中等', '偏快', '很快'])}`
      const basis = [`净利润同比 ${signedPct(profit.value)}`, equity && ok(equity.value) && `净资产同比 ${signedPct(equity.value)}`].filter(Boolean).join('，')
      return { text, basis }
    },
  },
  {
    key: 'size', title: '公司规模', factors: ['ln_market_cap'],
    headline(items) {
      const cap = find(items, 'ln_market_cap')
      if (!ok(shareOf(cap))) return null
      return { text: word(cap.market_share, ['很小', '偏小', '中等', '偏大', '很大']), basis: `总市值${FACTORS.ln_market_cap.format(cap.value)}，比 ${percent(cap.market_share)} 的公司大` }
    },
  },
]

// 一项因子在页面上的样子。
export function factorRow(item) {
  const info = FACTORS[item.name] || { label: item.display_name, format: fixed(3), higher: '高', what: '', rule: '' }
  const notComparable = info.cheap && ok(item.value) && item.value <= 0
  const position = (share, scope, noun) => (!ok(share) ? '' : notComparable ? '' : `${scope}比 ${percent(share)} 的${noun}${info.higher}`)
  return {
    name: item.name, label: info.label, original: item.display_name, value: info.format(item.value),
    level: notComparable ? null : level(item.market_share),
    levelWord: notComparable ? '没法比' : ok(item.market_share) ? (info.cheap ? ['很贵', '偏贵', '中等', '偏便宜', '很便宜'] : LEVELS)[level(item.market_share)] : '—',
    market: notComparable ? null : item.market_share, industry: notComparable ? null : item.industry_share,
    marketText: notComparable ? '亏损或为负，这一项没法比贵还是便宜' : position(item.market_share, '全市场', '股票'),
    industryText: position(item.industry_share, '同行业里', '股票'),
    ends: info.ends || ['低', '高'], what: info.what, rule: info.rule,
  }
}

// 全部因子 -> 七个方面（没有数据的方面不显示；不认识的因子放在最后的“其他”）。
export function aspectsFrom(items = []) {
  const known = new Set(ASPECTS.flatMap((a) => a.factors))
  const aspects = ASPECTS.map((aspect) => {
    const own = aspect.factors.map((name) => find(items, name)).filter(Boolean)
    const line = own.length ? aspect.headline(own) : null
    return own.length ? { key: aspect.key, title: aspect.title, text: line?.text || '数据不足', basis: line?.basis || '', rows: own.map(factorRow) } : null
  }).filter(Boolean)
  const others = items.filter((item) => !known.has(item.name))
  if (others.length) aspects.push({ key: 'other', title: '其他', text: `${others.length} 项`, basis: '', rows: others.map(factorRow) })
  return aspects
}

// “数据小结”里因子画像那一句。
export function aspectSummary(aspects = []) {
  const parts = aspects.filter((a) => a.key !== 'other' && a.text && a.text !== '数据不足').map((a) => `${a.title}：${a.text}`)
  return parts.length ? `${parts.join('；')}。` : ''
}
