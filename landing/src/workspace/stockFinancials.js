// 股票查询 → 财务：历期财报的数字格式、最新一期的卡片、趋势图可选的指标和没有财报时的说明。
import { num, ok, pct, signedPct, yi } from './researchReport.js'

export const shares = (value) => (ok(value) ? `${(value / 1e8).toLocaleString('zh-CN', { maximumFractionDigits: 2 })} 亿股` : '—')
export const points = (value) => (ok(value) ? `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)} 个百分点` : '—')
export const arrow = (value) => (!ok(value) ? '' : value > 1e-9 ? '↑' : value < -1e-9 ? '↓' : '→')
// 只表示比去年同期高还是低，不代表好坏（负债率高了不一定是坏事）。
export const changeTone = (value) => (!ok(value) ? 'text-slate-500' : value > 1e-9 ? 'text-sky-300' : value < -1e-9 ? 'text-amber-300' : 'text-slate-400')

// 历期财报表：每行一期，每列一个指标。cumulative：年初至报告期累计，不同季度之间不能直接比。
export const STATEMENT_COLUMNS = [
  { key: 'revenue', label: '营收', format: yi, cumulative: true },
  { key: 'revenue_yoy', label: '营收同比', format: signedPct },
  { key: 'net_profit', label: '净利润', format: yi, cumulative: true },
  { key: 'profit_yoy', label: '净利润同比', format: signedPct },
  { key: 'gross_margin', label: '毛利率', format: pct },
  { key: 'net_margin', label: '净利率', format: pct },
  { key: 'roe', label: '净资产收益率', format: pct, cumulative: true },
  { key: 'debt_ratio', label: '资产负债率', format: pct },
  { key: 'eps_ttm', label: '每股收益（近四季）', format: (v) => (ok(v) ? `${num(v, 2)} 元` : '—') },
  { key: 'current_ratio', label: '流动比率', format: (v) => num(v, 2) },
  { key: 'quick_ratio', label: '速动比率', format: (v) => num(v, 2) },
  { key: 'total_shares', label: '总股本', format: shares },
  { key: 'float_shares', label: '流通股本', format: shares },
]
export const column = (key) => STATEMENT_COLUMNS.find((item) => item.key === key)

// 最新一期的卡片：金额配同比增长，比率配和去年同期差几个百分点。
export const LATEST_CARDS = [
  { key: 'revenue', change: 'revenue_yoy', changeLabel: '同比' },
  { key: 'net_profit', change: 'profit_yoy', changeLabel: '同比' },
  { key: 'gross_margin', change: 'gross_margin', changeLabel: '比去年同期', ratio: true },
  { key: 'net_margin', change: 'net_margin', changeLabel: '比去年同期', ratio: true },
  { key: 'roe', change: 'roe', changeLabel: '比去年同期', ratio: true },
  { key: 'debt_ratio', change: 'debt_ratio', changeLabel: '比去年同期', ratio: true },
]
export function latestCards(latest) {
  if (!latest) return []
  return LATEST_CARDS.map((card) => {
    const meta = column(card.key)
    const change = card.ratio ? latest.changes?.[card.change] : latest[card.change]
    // 没有可比的数字时只显示“—”，原因放在鼠标提示里，卡片保持简短。
    const changeReason = ok(change) ? '' : card.ratio ? (latest.last_year ? '去年同期没有这一项' : '本地没有去年同期的财报') : (latest.missing?.[card.change] || '')
    return {
      key: card.key, label: meta.label, value: meta.format(latest[card.key]), reason: latest.missing?.[card.key] || '',
      changeLabel: card.changeLabel, changeText: card.ratio ? points(change) : signedPct(change), changeReason,
      arrow: arrow(change), tone: changeTone(change), known: ok(change),
    }
  })
}

// 趋势图：比率和同比可以直接跨季度比；累计的数字每年一季度会重新从零算起。
export const CHART_METRICS = ['profit_yoy', 'revenue_yoy', 'gross_margin', 'net_margin', 'debt_ratio', 'roe', 'net_profit', 'revenue']
export function chartSeries(rows = [], key) {
  const meta = column(key)
  const ordered = [...rows].reverse()
  return {
    labels: ordered.map((row) => row.period),
    series: [{ label: meta.label, color: '#a5b4fc', values: ordered.map((row) => (ok(row[key]) ? row[key] : null)) }],
    format: meta.format,
    zeroLine: key.endsWith('_yoy'),
    note: meta.cumulative ? `${meta.label}是年初至报告期累计的，每年一季度会重新从零算起，所以图上会呈锯齿状；要比较请看同一季度。` : '',
    points: ordered.filter((row) => ok(row[key])).length,
  }
}

// 本地有几期、从哪期到哪期；没有财报时说明原因和怎么补上。
export function coverageText(data) {
  if (!data?.periods) return ''
  return data.periods === 1 ? `本地有 1 期财报（${data.last_period}）` : `本地有 ${data.periods} 期财报（${data.first_period} ～ ${data.last_period}）`
}
export function emptyText(data, admin) {
  if (!data || data.periods) return ''
  const how = admin ? '可以在管理后台「数据更新 → 财务数据」里点“现在更新最近的财务数据”。' : '平台会在财报季定期更新财务数据。'
  if (data.empty_periods?.length) return `数据源确认这些报告期没有这只股票的财报：${data.empty_periods.join('、')}。多半是还没上市、长期停牌或已经退市。${how}`
  return `本地还没有这只股票的财报，可能是还没有下载到。${how}`
}
