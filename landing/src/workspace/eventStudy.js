// 事件研究页的显示规则：条件的默认值、写进链接的条件（从 AI研究员跳过来时预先填好）、
// 结果里“满足条件”和“全部交易日”的对照、以及从 AI研究员的数据表推出“这只股票现在的状态”。

const ok = (value) => typeof value === 'number' && Number.isFinite(value)
export const pct = (value, digits = 1) => (ok(value) ? `${(value * 100).toFixed(digits)}%` : '—')
export const signedPct = (value, digits = 2) => (ok(value) ? `${value > 0 ? '+' : ''}${(value * 100).toFixed(digits)}%` : '—')
// 涨跌的颜色：A 股习惯红涨绿跌。
export const tone = (value) => (!ok(value) || value === 0 ? 'text-slate-300' : value > 0 ? 'text-rose-300' : 'text-emerald-300')

// 新加一个条件时的默认值。
export function defaultCondition(kind) {
  const condition = { type: kind.type }
  if (kind.days?.length) condition.days = kind.days.includes(20) ? 20 : kind.days[0]
  if (kind.directions?.length) condition.direction = kind.directions[0].value
  if (kind.compare) Object.assign(condition, { op: kind.example < 0 ? '<=' : '>=', value: kind.example })
  return condition
}

// 条件写进链接：type:days:direction:op:value，多个条件用 | 分开。
export function encodePreset(conditions) {
  return (conditions || []).map((c) => [c.type, c.days ?? '', c.direction ?? '', c.op ?? '', c.value ?? ''].join(':')).join('|')
}
export function decodePreset(text, kinds = []) {
  const known = new Set(kinds.map((k) => k.type))
  return String(text || '').split('|').filter(Boolean).slice(0, 3).map((part) => {
    const [type, days, direction, op, value] = part.split(':')
    const condition = { type }
    if (days) condition.days = Number(days)
    if (direction) condition.direction = direction
    if (op) condition.op = op
    if (value !== undefined && value !== '') condition.value = Number(value)
    return condition
  }).filter((c) => !known.size || known.has(c.type))
}

// 对照表的一行：满足条件 vs 全部交易日，以及差多少。
export function compareRows(horizon) {
  if (!horizon?.events?.count) return []
  const ev = horizon.events
  const all = horizon.all || {}
  return [
    { label: '平均涨跌', event: signedPct(ev.mean), all: signedPct(all.mean), diff: ok(ev.mean) && ok(all.mean) ? ev.mean - all.mean : null, signed: true },
    { label: '中位数', event: signedPct(ev.median), all: signedPct(all.median), diff: ok(ev.median) && ok(all.median) ? ev.median - all.median : null, signed: true },
    { label: '上涨的比例', event: pct(ev.up_share), all: pct(all.up_share), diff: ok(ev.up_share) && ok(all.up_share) ? ev.up_share - all.up_share : null, points: true },
    { label: '中间一半落在', event: `${signedPct(ev.p25, 1)} ～ ${signedPct(ev.p75, 1)}`, all: `${signedPct(all.p25, 1)} ～ ${signedPct(all.p75, 1)}`, diff: null },
  ]
}
export const diffText = (row) => (!ok(row.diff) ? '' : row.points ? `${row.diff > 0 ? '+' : ''}${(row.diff * 100).toFixed(1)} 个百分点` : signedPct(row.diff))

// 一句话说明结果，只描述历史，不下结论。
export function headline(result) {
  if (!result) return ''
  const h = result.horizons?.[String(result.main_horizon)]
  if (!result.events || !h?.events?.count) return `这段时间里没有满足条件的情况。`
  const ex = h.excess
  const parts = [`${result.start} 至 ${result.end}，${result.scope}共出现 ${result.events.toLocaleString('zh-CN')} 次（${result.stocks.toLocaleString('zh-CN')} 只股票）`,
    `之后 ${result.main_horizon} 个交易日平均 ${signedPct(h.events.mean)}，全部交易日平均 ${signedPct(h.all.mean)}`]
  if (ok(ex?.mean)) parts.push(`扣掉同一天全部股票的平均以后是 ${signedPct(ex.mean)}`)
  return `${parts.join('；')}。`
}

// 分布图两组柱子的高度（相对最高的那一格）。
export function histogramBars(histogram) {
  const top = Math.max(0, ...(histogram?.events || []), ...(histogram?.all || []))
  return (histogram?.labels || []).map((label, i) => ({
    label, event: histogram.events[i] || 0, all: histogram.all[i] || 0,
    eventHeight: top ? Math.round(((histogram.events[i] || 0) / top) * 100) : 0,
    allHeight: top ? Math.round(((histogram.all[i] || 0) / top) * 100) : 0,
  }))
}

// AI研究员的数据表 -> 这只股票现在满足的几个状态，每个都可以在事件研究里看全市场的历史。
// 阈值取整到常用的数，只列明显的状态。
export function statesFromFacts(facts) {
  const value = (key) => (facts || []).find((f) => f.key === key)?.value
  const states = []
  const fall = value('ret_20d')
  if (ok(fall) && fall <= -0.15) states.push({ text: `近 20 个交易日跌了 ${Math.round(-fall * 100)}%`, conditions: [{ type: 'ret', days: 20, op: '<=', value: -15 }] })
  if (ok(fall) && fall >= 0.15) states.push({ text: `近 20 个交易日涨了 ${Math.round(fall * 100)}%`, conditions: [{ type: 'ret', days: 20, op: '>=', value: 15 }] })
  const high = value('from_high_250d')
  if (ok(high) && high <= -0.2) {
    const level = Math.floor(-high * 10) * 10
    states.push({ text: `距近一年最高价 ${Math.round(high * 100)}%`, conditions: [{ type: 'from_high', op: '<=', value: -level }] })
  }
  const ma60 = value('ma60_gap')
  if (ok(ma60)) states.push({ text: ma60 >= 0 ? '收盘价在 60 日均线上方' : '收盘价在 60 日均线下方', conditions: [{ type: 'ma_gap', days: 60, op: ma60 >= 0 ? '>=' : '<=', value: 0 }] })
  const amount = value('amount_ratio')
  if (ok(amount) && amount >= 2) states.push({ text: `当日成交额是近 20 日平均的 ${amount.toFixed(1)} 倍`, conditions: [{ type: 'amount_ratio', op: '>=', value: 2 }] })
  const pe = value('pe_ttm')
  if (ok(pe) && pe > 0) {
    const cap = pe <= 15 ? 15 : pe <= 30 ? 30 : null
    if (cap) states.push({ text: `市盈率 ${pe.toFixed(1)}`, conditions: [{ type: 'pe', op: '<=', value: cap }] })
    else if (pe >= 60) states.push({ text: `市盈率 ${pe.toFixed(1)}`, conditions: [{ type: 'pe', op: '>=', value: 60 }] })
  }
  const growth = value('profit_growth')
  if (ok(growth) && Math.abs(growth) >= 0.3) {
    states.push({ text: `最新财报净利润同比 ${signedPct(growth, 0)}`, conditions: [{ type: 'profit_yoy', op: growth > 0 ? '>=' : '<=', value: growth > 0 ? 30 : -30 }] })
  }
  return states.slice(0, 5)
}
