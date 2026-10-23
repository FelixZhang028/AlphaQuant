// K 线图的数据整理：与图表库无关，便于单独测试。

const RANGE_MONTHS = { '3m': 3, '1y': 12, '3y': 36 }

export function toCandles(bars) {
  return bars.map((bar) => ({
    // 本地零点：图表按浏览器时区显示，日期不会偏移一天。
    timestamp: new Date(`${bar.date}T00:00:00`).getTime(),
    open: bar.open, high: bar.high, low: bar.low, close: bar.close, volume: bar.volume,
  }))
}

// 以最后一根 K 线为终点，统计所选范围内的 K 线数量；未知范围视为全部。
export function barsInRange(bars, range) {
  const months = RANGE_MONTHS[range]
  if (!months || !bars.length) return bars.length
  const [year, month, day] = bars[bars.length - 1].date.split('-').map(Number)
  const start = new Date(year, month - 1 - months, day)
  const cutoff = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(start.getDate()).padStart(2, '0')}`
  let count = 0
  for (let index = bars.length - 1; index >= 0 && bars[index].date > cutoff; index--) count++
  return count
}

// 把日线合并成周线或月线：开盘取第一天，收盘取最后一天，日期取该周期最后一个交易日。
export function aggregateBars(bars, period) {
  if (period !== 'week' && period !== 'month') return bars
  const result = []
  let current = ''
  for (const bar of bars) {
    const key = period === 'month' ? bar.date.slice(0, 7) : weekStart(bar.date)
    if (key !== current) {
      current = key
      result.push({ ...bar })
      continue
    }
    const merged = result[result.length - 1]
    merged.date = bar.date
    merged.high = Math.max(merged.high, bar.high)
    merged.low = Math.min(merged.low, bar.low)
    merged.close = bar.close
    merged.volume += bar.volume
  }
  return result
}

function weekStart(date) {
  const [year, month, day] = date.split('-').map(Number)
  const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay()
  return new Date(Date.UTC(year, month - 1, day - ((weekday + 6) % 7))).toISOString().slice(0, 10)
}

// 最新一根日线及按交易日计算的区间涨跌；历史不够长的区间返回 null，不用更短的区间代替。
export function quoteSummary(bars) {
  if (!bars.length) return null
  const last = bars[bars.length - 1]
  const since = (sessions) => (bars.length > sessions ? last.close / bars[bars.length - 1 - sessions].close - 1 : null)
  return {
    date: last.date, open: last.open, high: last.high, low: last.low, close: last.close, volume: last.volume,
    change: bars.length > 1 ? last.close - bars[bars.length - 2].close : null,
    changePct: since(1), pct20: since(20), pct60: since(60), pct250: since(250),
  }
}

// 第一根日期不早于 date 的 K 线：周线、月线的日期是该周期最后一个交易日，所以它就是 date 所在的那一根。
function barOnOrAfter(shown, date) {
  let low = 0
  let high = shown.length
  while (low < high) {
    const middle = (low + high) >> 1
    if (shown[middle].date < date) low = middle + 1
    else high = middle
  }
  return shown[low]
}

// 把一次回测在这只股票上的记录换算到当前图表。
// bars 是接口返回的日线（含每天的复权比例 factor），shown 是当前周期实际画出的 K 线。
// 成交价是不复权的真实价格，乘以当天的复权比例后才能和图上的价格对齐。
export function tradeMarks(bars, shown, trades) {
  const daily = new Map(bars.map((bar) => [bar.date, bar]))
  const marks = []
  let missing = 0
  const add = (record, kind, price) => {
    const day = daily.get(record.date)
    const bar = day && barOnOrAfter(shown, record.date)
    if (!bar) return missing++
    const buy = record.side === 'BUY'
    marks.push({ kind, buy, date: bar.date, value: price(day), anchor: buy ? bar.low : bar.high })
  }
  for (const fill of trades.fills) add(fill, fill.side === 'BUY' ? 'buy' : 'sell', (day) => fill.price * day.factor)
  // 未成交的订单没有成交价，只标在 K 线外侧。
  for (const order of trades.rejected) add(order, 'reject', () => null)
  const spans = []
  for (const holding of trades.holdings) {
    const start = barOnOrAfter(shown, holding.start_date)
    const end = barOnOrAfter(shown, holding.end_date) || shown[shown.length - 1]
    if (start && end && start.date <= end.date) spans.push({ start: start.date, end: end.date })
  }
  return { marks, spans, missing }
}

// 指数代码带交易所后缀（000001.SH 是上证指数），股票是 6 位数字（000001 是平安银行）。
export function isIndexSymbol(code) {
  return /^\d{6}\.[A-Z]+$/i.test(String(code || ''))
}

// K线下方的说明：价格口径、日期范围，以及没有画出来的记录。wanted 是用户选的复权方式。
export function klineCaption(data, wanted) {
  if (!data?.bars?.length) return ''
  const index = data.kind === 'index'
  const basis = index ? '指数' : data.adjust === 'forward' ? '前复权' : '不复权'
  const parts = [`${basis} · ${data.start_date} 至 ${data.end_date} · 共 ${data.bars.length} 个交易日 · 成交量单位：股`]
  if (!index && wanted === 'forward' && data.adjust !== 'forward') parts.push('该股票缺少复权因子，当前显示不复权价格')
  if (data.suspended_days) parts.push(`停牌 ${data.suspended_days} 天未显示`)
  if (data.invalid_rows) parts.push(`${data.invalid_rows} 条记录价格不完整未显示`)
  return parts.join('；')
}

export function formatVolume(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return String(value)
  // Number() 去掉多余的 0：6000.00万 显示为 6000万。
  if (Math.abs(number) >= 1e8) return `${Number((number / 1e8).toFixed(2))}亿`
  if (Math.abs(number) >= 1e4) return `${Number((number / 1e4).toFixed(2))}万`
  return String(Math.round(number))
}
