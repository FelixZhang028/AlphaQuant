// 事件研究页的显示规则：条件的默认值、写进链接的条件（从 AI研究员跳过来时预先填好）、条件写成一句话、
// 结果里“满足条件”和“全部交易日”的对照、几句话的读法、走势图和每年的柱子，
// 以及从 AI研究员的数据表推出“这只股票现在的状态”。

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

// 分布图两组柱子的高度（相对最高的那一格）。
export function histogramBars(histogram) {
  const top = Math.max(0, ...(histogram?.events || []), ...(histogram?.all || []))
  return (histogram?.labels || []).map((label, i) => ({
    label, event: histogram.events[i] || 0, all: histogram.all[i] || 0,
    eventHeight: top ? Math.round(((histogram.events[i] || 0) / top) * 100) : 0,
    allHeight: top ? Math.round(((histogram.all[i] || 0) / top) * 100) : 0,
  }))
}

// ---------------------------------------------------------------- 条件写成一句话

// 条件种类在句子里的简短说法（下拉框里显示）。
export const SHORT_NAMES = {
  ret: '涨跌幅', from_high: '离一年最高价', from_low: '离一年最低价', ma_gap: '和均线的距离', ma_cross: '穿过均线',
  limit: '涨停或跌停', amount_ratio: '成交额放大', turnover: '换手率', pe: '市盈率', pb: '市净率',
  profit_yoy: '净利润同比', roe: '净资产收益率',
}
export const OP_WORDS = { '<=': '不超过', '>=': '不低于' }

// 选好种类以后，句子后面的几段：文字、天数、方向、比较、数值。
export function sentenceParts(kind) {
  if (!kind) return []
  const text = (value) => ({ part: 'text', text: value })
  const compare = [{ part: 'op' }, { part: 'value' }, ...(kind.unit ? [text(kind.unit)] : [])]
  switch (kind.type) {
    case 'ret': return [text('近'), { part: 'days' }, text('个交易日'), ...compare]
    case 'ma_gap': return [text('收盘价相对'), { part: 'days' }, text('日均线'), ...compare]
    case 'ma_cross': return [text('收盘价当天'), { part: 'direction' }, { part: 'days' }, text('日均线')]
    case 'limit': return [text('当天'), { part: 'direction' }]
    case 'amount_ratio': return [text('当天成交额是近 20 日平均的'), ...compare]
    case 'pe': return [text('（只算盈利的公司）'), ...compare]
    case 'roe': return [text('（最新财报，年初至报告期）'), ...compare]
    case 'profit_yoy': return [text('（最新财报）'), ...compare]
    default: return compare
  }
}

// ---------------------------------------------------------------- 结果怎么读

const CLOSE = 0.005           // 差不到 0.5 个百分点，算“差不多”
const MIN_YEAR_EVENTS = 10    // 一年里至少这么多次，才拿来比
const points = (value) => `${(Math.abs(value) * 100).toFixed(1)} 个百分点`

// 三个大数字：之后平均涨跌、上涨的比例、和同一天全部股票比。
export function bigNumbers(horizonKey, h) {
  if (!h?.events?.count) return []
  const ev = h.events
  const all = h.all || {}
  const ex = h.excess || {}
  return [
    { label: `之后 ${horizonKey} 个交易日平均涨跌`, value: signedPct(ev.mean, 1), tone: tone(ev.mean), note: `平时 ${signedPct(all.mean, 1)}` },
    { label: '上涨的比例', value: pct(ev.up_share, 0), tone: 'text-white', note: `平时 ${pct(all.up_share, 0)}` },
    { label: '和同一天的全部股票比', value: signedPct(ex.mean, 1), tone: tone(ex.mean), note: `跑赢的占 ${pct(ex.up_share, 0)}` },
  ]
}

// 几句话读结果：和平时比、和同一天的全部股票比、每年是不是都这样。只描述历史。
export function reading(result, horizonKey) {
  const h = result?.horizons?.[String(horizonKey)]
  if (!result?.events || !h?.events?.count) return '这段时间里没有满足条件的情况。'
  const m = h.events.mean
  const a = h.all?.mean
  const x = h.excess?.mean
  const sentences = [`历史上出现过 ${result.events.toLocaleString('zh-CN')} 次。`]
  let first = `之后 ${horizonKey} 个交易日`
  const diff = ok(m) && ok(a) ? m - a : null
  if (ok(diff)) first += Math.abs(diff) < CLOSE ? `的平均涨跌和平时差不多` : `平均比平时${diff > 0 ? '高' : '低'} ${points(diff)}`
  if (ok(x)) {
    if (Math.abs(x) < CLOSE) {
      first += ok(diff) && Math.abs(diff) >= CLOSE
        ? `，但主要是因为那段时间大部分股票也在${m - x > a ? '涨' : '跌'}；和同一天的全部股票比，差不多。`
        : `；和同一天的全部股票比，也差不多。`
    } else {
      first += `；和同一天的全部股票比，平均${x > 0 ? '高' : '低'} ${points(x)}，跑赢的占 ${pct(h.excess.up_share, 0)}。`
    }
  } else first += '。'
  sentences.push(first)
  if (String(horizonKey) === String(result.main_horizon)) {
    const years = (result.by_year || []).filter((y) => y.events >= MIN_YEAR_EVENTS && ok(y.mean) && ok(y.all_mean))
    if (years.length >= 3) {
      const higher = years.filter((y) => y.mean - y.all_mean >= CLOSE).length
      const lower = years.filter((y) => y.mean - y.all_mean <= -CLOSE).length
      const similar = years.length - higher - lower
      const all = (count) => count === years.length
      const counts = [higher && `${higher} 年比平时高`, lower && `${lower} 年比平时低`, similar && `${similar} 年和平时差不多`].filter(Boolean)
      sentences.push(`次数够多的 ${years.length} 年里，${all(higher) ? '每一年都比平时高' : all(lower) ? '每一年都比平时低' : all(similar) ? '每一年都和平时差不多' : counts.join('，')}。`)
    }
  }
  if (result.events < 30) sentences.push('次数太少，结果很不稳定，看看就好。')
  return sentences.join('')
}

// ---------------------------------------------------------------- 走势图、每年的柱子

function niceStep(span) {
  const steps = [0.005, 0.01, 0.02, 0.025, 0.05, 0.1, 0.2, 0.25, 0.5, 1]
  return steps.find((s) => span / s <= 5) || 1
}

// 之后每一天的平均累计涨跌：三条线的 SVG 路径、纵轴刻度、每一天的横坐标。
export const PATH_LINES = ['events', 'market', 'all']
export function pathChart(path, { width = 640, height = 220, left = 48, right = 12, top = 12, bottom = 26 } = {}) {
  if (!path?.days?.length) return null
  const days = path.days
  const values = PATH_LINES.flatMap((key) => (path[key] || []).filter(ok))
  let low = Math.min(0, ...values)
  let high = Math.max(0, ...values)
  if (high - low < 0.01) { high += 0.005; low -= 0.005 }
  const step = niceStep(high - low)
  low = Math.floor(low / step) * step
  high = Math.ceil(high / step) * step
  const lastDay = days[days.length - 1]
  const x = (day) => left + (day / lastDay) * (width - left - right)
  const y = (value) => top + ((high - value) / (high - low)) * (height - top - bottom)
  const line = (key) => {
    let d = ''
    let open = false
    days.forEach((day, i) => {
      const v = path[key]?.[i]
      if (!ok(v)) { open = false; return }
      d += `${open ? 'L' : 'M'}${x(day).toFixed(1)} ${y(v).toFixed(1)} `
      open = true
    })
    return d.trim()
  }
  const ticks = []
  for (let v = low; v <= high + 1e-9; v += step) ticks.push({ y: y(v), label: Math.abs(v) < 1e-9 ? '0%' : signedPct(v, step < 0.01 ? 1 : 0), zero: Math.abs(v) < 1e-9 })
  return {
    width, height, left, right, top, bottom, ticks,
    lines: Object.fromEntries(PATH_LINES.map((key) => [key, line(key)])),
    xs: days.map(x), days,
    point: (key, day) => { const i = days.indexOf(Number(day)); const v = path[key]?.[i]; return ok(v) ? { x: x(Number(day)), y: y(v), value: v } : null },
    x,
  }
}

// 每一年的平均涨跌（满足条件以后）的柱子，和那一年“平时”的位置；次数太少的年份画淡一些。
export function yearChart(byYear, { width = 640, height = 160, top = 14, bottom = 22, gap = 6 } = {}) {
  const years = (byYear || []).filter((y) => ok(y.mean))
  if (!years.length) return null
  // 纵轴只留有数据的那一侧：都在涨的话 0 线在下面，柱子能画得高一些。
  const values = years.flatMap((y) => [y.mean, ok(y.all_mean) ? y.all_mean : 0])
  const high = Math.max(0, ...values)
  const low = Math.min(0, ...values)
  const scale = (height - top - bottom) / Math.max(0.01, high - low)
  const zero = top + high * scale
  const slot = width / years.length
  const w = Math.max(4, slot - gap)
  return {
    width, height, zero,
    bars: years.map((y, i) => {
      const h = Math.abs(y.mean) * scale
      return {
        year: y.year, events: y.events, mean: y.mean, all_mean: y.all_mean, few: y.events < MIN_YEAR_EVENTS,
        x: i * slot + (slot - w) / 2, w, y: y.mean >= 0 ? zero - h : zero, h: Math.max(1, h), up: y.mean >= 0,
        allY: ok(y.all_mean) ? zero - y.all_mean * scale : null, center: i * slot + slot / 2,
      }
    }),
  }
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
