// AI研究员数据报告最上面的“短期分析 / 长期分析”：按固定规则把下面各节的数据整理成几条话。
// 只写事实、历史统计和要跟踪的数字，每条都标出依据在哪一节；
// 不出现买入、卖出、持有、目标价、看涨、看跌，不预测这只股票以后会怎样。

import { aspectsFrom } from './factorProfile.js'
import { pct, signedPct } from './researchReport.js'

const ok = (value) => typeof value === 'number' && Number.isFinite(value)
const SHORT_CHECKS = ['st', 'suspended', 'limit_down', 'liquidity', 'drawdown', 'new_listing']
const LONG_CHECKS = ['loss', 'profit_drop', 'debt', 'profit_trend']
const percent = (share) => `${Math.round(share * 100)}%`

const aspectMap = (report) => Object.fromEntries(aspectsFrom(report?.factors?.items || []).map((a) => [a.key, a]))
const warnings = (report, keys) => (report?.checks || []).filter((c) => c.state === 'warn' && keys.includes(c.key))
const factorValue = (report, name) => (report?.factors?.items || []).find((i) => i.name === name)?.value

// 事件研究的结果 -> 一句话（study：{ loading, error, result, label }）。
export function historyText(study) {
  if (!study) return ''
  if (study.loading) return '正在统计全市场历史上类似的情况……'
  if (study.error) return `没能统计历史上类似的情况：${study.error}`
  const r = study.result
  const h = r?.horizons?.[String(r?.main_horizon)]
  if (!r?.events || !h?.events?.count) return `历史上全市场没有足够的“${study.label}”可以统计。`
  const parts = [`历史上全市场“${r.conditions.join('，并且 ')}”出现过 ${r.events.toLocaleString('zh-CN')} 次`,
    `之后 ${r.main_horizon} 个交易日平均 ${signedPct(h.events.mean)}（平时 ${signedPct(h.all?.mean)}），上涨的占 ${pct(h.events.up_share, 0)}`]
  if (ok(h.excess?.mean)) parts.push(`和同一天的全部股票比 ${signedPct(h.excess.mean)}`)
  return `${parts.join('；')}。`
}

// 短期（几天到一个月）：现在的状态、历史上类似的情况、要留意的。
export function shortAnalysis(report, study) {
  const a = aspectMap(report)
  const items = []
  const state = [a.trend?.text, a.volatility && `波动${a.volatility.text}`, a.heat && `交易${a.heat.text}`].filter((t) => t && !t.includes('数据不足'))
  if (state.length) items.push({ key: 'state', title: '现在的状态', text: `${state.join('；')}。`, basis: a.trend?.basis || '', target: 'report-factors' })
  if (study) items.push({ key: 'history', title: '历史上类似的情况', text: historyText(study), basis: '全市场很多股票的历史统计，不是对这只股票的预测', target: 'event-study' })
  const notes = warnings(report, SHORT_CHECKS).map((c) => c.text)
  if (a.volatility && ['偏大', '很大'].includes(a.volatility.text)) notes.push('波动大，短期上涨和下跌都可能很剧烈')
  items.push({ key: 'watch', title: '要留意的', text: notes.length ? `${notes.join('；')}。` : '按短期的几条规则检查，没有发现需要特别留意的地方。', basis: '', target: 'report-checks' })
  return items
}

// 估值在自己近几年里的位置（市盈率优先，亏损时用市净率）。
function ownValuation(report) {
  const valuation = report?.charts?.valuation
  const pick = [['pe_ttm', '市盈率'], ['pb_mrq', '市净率']].find(([key]) => ok(valuation?.bands?.[key]?.share) && ok(valuation.bands[key].current))
  if (!pick) return ''
  const [key, name] = pick
  const band = valuation.bands[key]
  const where = band.share >= 0.8 ? '偏高的位置' : band.share <= 0.2 ? '偏低的位置' : '中间的位置'
  const since = valuation.start ? ` ${valuation.start.slice(0, 4)} 年以来` : '近几年'
  return `${name} ${band.current.toFixed(key === 'pb_mrq' ? 2 : 1)} 倍，在它自己${since}的历史里处在${where}（比 ${percent(band.share)} 的交易日高）`
}

// 长期（一年以上）：估值、基本面、接下来要跟踪的数字。
export function longAnalysis(report) {
  const a = aspectMap(report)
  const trends = report?.financial_trend?.trends || {}
  const rows = report?.financial_trend?.rows || []
  const latest = rows[rows.length - 1] || {}
  const items = []

  const own = ownValuation(report)
  const market = a.value && a.value.text !== '数据不足' ? `和全市场比：${a.value.text}` : ''
  if (own || market) items.push({ key: 'value', title: '估值', text: `${[own, market].filter(Boolean).join('；')}。`, basis: '', target: own ? 'report-valuation' : 'report-factors' })

  const longNotes = warnings(report, LONG_CHECKS).map((c) => c.text)
  const losing = a.quality?.text?.startsWith('亏损')
  const quality = !a.quality || a.quality.text === '数据不足' ? null
    : losing ? (warnings(report, ['loss']).length ? null : `目前亏损${a.quality.text.slice(2)}`) : `赚钱能力${a.quality.text}`
  const base = [quality, a.growth && a.growth.text !== '数据不足' && a.growth.text].filter(Boolean)
  if (trends.profit_yoy === '连续上升' || trends.profit_yoy === '连续下降') base.push(`最近四份财报的利润增速${trends.profit_yoy}`)
  if (trends.debt_ratio === '连续上升') base.push('资产负债率连续上升')
  if (base.length || longNotes.length) {
    items.push({ key: 'fundamentals', title: '基本面', text: `${base.join('；')}${base.length ? '。' : ''}${longNotes.length ? `需要留意：${longNotes.join('；')}。` : ''}`,
      basis: a.quality?.basis || '', target: rows.length ? 'report-trend' : 'report-factors' })
  }

  const track = []
  const roe = factorValue(report, 'roe_ttm')
  if (ok(roe)) track.push(roe > 0 ? `净资产收益率能不能保持在 ${pct(roe, 0)} 左右` : '什么时候能扭亏为盈')
  const growth = ok(latest.profit_yoy) ? latest.profit_yoy : factorValue(report, 'yoy_net_profit')
  if (ok(growth)) track.push(growth >= 0.3 ? `利润的高增长（${signedPct(growth)}）能不能持续` : growth < 0 ? `利润下滑（${signedPct(growth)}）有没有止住` : `利润增速（${signedPct(growth)}）是加快还是放慢`)
  const debt = ok(latest.debt_ratio) ? latest.debt_ratio : factorValue(report, 'debt_ratio')
  if (ok(debt) && (trends.debt_ratio === '连续上升' || warnings(report, ['debt']).length)) track.push(`资产负债率（${pct(debt, 0)}）有没有继续上升`)
  const cash = factorValue(report, 'cfp_ttm')
  if (ok(cash) && cash <= 0) track.push('经营现金流能不能转正')
  if (own.includes('偏高的位置')) track.push('估值在近几年偏高，利润增长能不能跟上')
  if (track.length) items.push({ key: 'track', title: '接下来要跟踪的', text: `之后几份财报里值得看：${track.slice(0, 3).join('；')}。`, basis: '', target: rows.length ? 'report-trend' : 'report-factors' })
  return items
}
