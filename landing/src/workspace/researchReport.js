// AI 研究员的数据报告（不用 AI）：数字格式、留意清单、财务趋势、同行对比和图表的显示规则。
// 因子画像的显示规则在 factorProfile.js。

export const ok = (value) => typeof value === 'number' && Number.isFinite(value)
export const pct = (value, digits = 1) => (ok(value) ? `${(value * 100).toFixed(digits)}%` : '—')
export const signedPct = (value, digits = 1) => (ok(value) ? `${value >= 0 ? '+' : ''}${(value * 100).toFixed(digits)}%` : '—')
export const num = (value, digits = 2) => (ok(value) ? value.toFixed(digits) : '—')
export const yi = (value) => (ok(value) ? `${(value / 1e8).toLocaleString('zh-CN', { maximumFractionDigits: value >= 1e10 ? 0 : 1 })} 亿` : '—')

// 留意清单：需要留意的排在前面，然后是数据不足的，最后是没有发现问题的。
const CHECK_ORDER = { warn: 0, unknown: 1, ok: 2 }
export const CHECK_LABELS = { warn: '需要留意', unknown: '数据不足', ok: '没有发现' }
export function sortedChecks(checks = []) {
  return [...checks].sort((a, b) => (CHECK_ORDER[a.state] ?? 3) - (CHECK_ORDER[b.state] ?? 3))
}
export function checkCounts(checks = []) {
  return checks.reduce((counts, item) => ({ ...counts, [item.state]: (counts[item.state] || 0) + 1 }), {})
}

// 财务趋势表：每行一个指标，每列一个报告期。
export const FINANCE_ROWS = [
  { key: 'revenue_yoy', label: '营收同比', format: signedPct },
  { key: 'profit_yoy', label: '净利润同比', format: signedPct },
  { key: 'gross_margin', label: '毛利率', format: pct },
  { key: 'net_margin', label: '净利率', format: pct },
  { key: 'roe', label: '净资产收益率（年初至报告期）', format: pct, note: '年初至报告期累计，不同季度不能直接比较' },
  { key: 'debt_ratio', label: '资产负债率', format: pct },
]
export function trendTone(word) {
  return { 连续上升: 'text-sky-300', 连续下降: 'text-amber-300', 基本持平: 'text-slate-300', 有升有降: 'text-slate-400' }[word] || 'text-slate-500'
}

// 同行对比表的列。
export const PEER_COLUMNS = [
  { key: 'market_cap', label: '总市值', format: yi },
  { key: 'pe', label: '市盈率', format: (v) => num(v, 1) },
  { key: 'pb', label: '市净率', format: (v) => num(v, 2) },
  { key: 'roe', label: '净资产收益率', format: pct },
  { key: 'profit_yoy', label: '净利润同比', format: signedPct },
  { key: 'debt_ratio', label: '资产负债率', format: pct },
  { key: 'ret_60d', label: '近 60 日涨跌', format: signedPct },
]

// 图表：日期、各条线的数值；事件放到对应的日期上。
export function priceSeries(prices = []) {
  return {
    labels: prices.map((row) => row[0]),
    series: [
      { label: '收盘价（复权）', color: '#a5b4fc', values: prices.map((row) => row[1]) },
      { label: '20 日均线', color: '#fbbf24', values: prices.map((row) => row[2]) },
      { label: '60 日均线', color: '#34d399', values: prices.map((row) => row[3]) },
    ],
  }
}
export const EVENT_LABELS = { action: '分红送转', report: '财报', index: '指数', industry: '行业', st: 'ST' }
export function eventMarkers(labels = [], events = []) {
  return events
    .map((event) => {
      // 落在没有行情的日子（例如周末公告）时，标在之后的第一个交易日。
      const index = labels.findIndex((day) => day >= event.date)
      return index < 0 ? null : { index, kind: event.kind, text: `${event.date} ${event.text}` }
    })
    .filter(Boolean)
}
export function valuationSeries(valuation, key) {
  const column = key === 'pb_mrq' ? 2 : 1
  const points = valuation?.points || []
  const band = valuation?.bands?.[key]
  return {
    labels: points.map((row) => row[0]),
    series: [{ label: key === 'pb_mrq' ? '市净率' : '市盈率（TTM）', color: '#a5b4fc', values: points.map((row) => row[column]) }],
    bands: band ? [
      { label: '20% 分位', value: band.p20, color: '#34d399' },
      { label: '中位数', value: band.p50, color: '#94a3b8' },
      { label: '80% 分位', value: band.p80, color: '#f59e0b' },
    ] : [],
    band,
  }
}
export function trendSeries(trend) {
  const rows = trend?.rows || []
  return {
    labels: rows.map((row) => row.period),
    series: [
      { label: '营收同比', color: '#a5b4fc', values: rows.map((row) => row.revenue_yoy) },
      { label: '净利润同比', color: '#fbbf24', values: rows.map((row) => row.profit_yoy) },
    ],
  }
}
