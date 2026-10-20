// 功能台首页的显示规则：问候语、涨跌的颜色（A 股习惯：红涨绿跌）、数字格式、小走势图、
// 涨跌分布、股票池排序、最近的研究的时间、新手任务的进度、财报季和每日更新的说法。

const ok = (value) => typeof value === 'number' && Number.isFinite(value)

export function greeting(now = new Date()) {
  const hour = now.getHours()
  return hour < 5 ? '夜深了' : hour < 11 ? '早上好' : hour < 13 ? '中午好' : hour < 18 ? '下午好' : '晚上好'
}
const WEEKDAYS = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六']
export function todayText(now = new Date()) {
  return `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日 ${WEEKDAYS[now.getDay()]}`
}

export const tone = (value) => (!ok(value) || value === 0 ? 'text-slate-300' : value > 0 ? 'text-rose-300' : 'text-emerald-300')
export const signedPct = (value, digits = 2) => (ok(value) ? `${value > 0 ? '+' : ''}${(value * 100).toFixed(digits)}%` : '—')
export const price = (value) => (ok(value) ? value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—')
export function amountText(value) {
  if (!ok(value)) return '—'
  return value >= 1e12 ? `${(value / 1e12).toFixed(2)} 万亿` : `${(value / 1e8).toFixed(0)} 亿`
}

// 小走势图：把一串收盘价画进 100 × 30 的框里；数据不够两个点时不画。
export function sparkPath(series, width = 100, height = 30) {
  const values = (series || []).filter(ok)
  if (values.length < 2) return ''
  const min = Math.min(...values)
  const span = Math.max(...values) - min || 1
  const step = width / (values.length - 1)
  return values.map((v, i) => `${i ? 'L' : 'M'}${(i * step).toFixed(1)},${(height - ((v - min) / span) * height).toFixed(1)}`).join(' ')
}

// 涨跌分布条：上涨、平盘、下跌各占多少。
export function breadthShares(breadth) {
  const total = (breadth?.up || 0) + (breadth?.flat || 0) + (breadth?.down || 0)
  if (!total) return null
  const share = (n) => Math.round((n / total) * 1000) / 10
  return { up: share(breadth.up), flat: share(breadth.flat), down: share(breadth.down) }
}

// 股票池排序：没有行情的排在最后。
export function sortPool(rows, key = '', descending = true) {
  if (!key) return [...(rows || [])]
  return [...(rows || [])].sort((a, b) => {
    const x = a[key]
    const y = b[key]
    if (!ok(x) && !ok(y)) return 0
    if (!ok(x)) return 1
    if (!ok(y)) return -1
    return descending ? y - x : x - y
  })
}

// 最近的研究的时间：今天只写几点，昨天写“昨天”，更早写日期。时间按本机时区显示。
export function whenText(iso, now = new Date()) {
  const at = new Date(iso)
  if (Number.isNaN(at.getTime())) return ''
  const day = (d) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  const clock = `${String(at.getHours()).padStart(2, '0')}:${String(at.getMinutes()).padStart(2, '0')}`
  if (day(at) === day(now)) return `今天 ${clock}`
  if (day(at) === day(yesterday)) return `昨天 ${clock}`
  return at.getFullYear() === now.getFullYear() ? `${at.getMonth() + 1}月${at.getDate()}日` : `${at.getFullYear()}-${at.getMonth() + 1}-${at.getDate()}`
}
export const KIND_TONES = { backtest: 'bg-indigo-500/15 text-indigo-200', brief: 'bg-violet-500/15 text-violet-200', chat: 'bg-sky-500/15 text-sky-200', strategy: 'bg-amber-500/15 text-amber-200' }

export function stepsProgress(steps) {
  const list = steps || []
  const done = list.filter((step) => step.done).length
  return { done, total: list.length, finished: list.length > 0 && done === list.length, next: list.find((step) => !step.done) || null }
}

// 数据日历的几句话。
export function dailyText(daily) {
  if (!daily) return ''
  const data = daily.data_date ? `行情更新到 ${daily.data_date}` : '还没有行情数据'
  if (daily.enabled === false) return `${data} · 自动更新已关闭`
  return `${data} · 每个交易日 ${daily.time || '18:30'} 以后自动更新`
}
export function seasonText(season) {
  if (!season) return ''
  const left = season.days_left > 0 ? `还有 ${season.days_left} 天` : '今天截止'
  return `${season.period}最晚 ${season.deadline} 公布（${left}），已公布 ${season.published.toLocaleString('zh-CN')} 家`
}
export function seasonShare(season) {
  if (!season?.listed) return 0
  return Math.min(100, Math.round((season.published / season.listed) * 100))
}

// 点行业时在 AI 问答里问的话：只问数据，不问买卖。
export const industryQuestion = (name) => `${name}这个行业现在的估值和财务情况怎么样？`
