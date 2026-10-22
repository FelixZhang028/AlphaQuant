// 积分页面上的说法：到期时间、明细的一行、价格表的一行。都是纯函数，方便测试。

const CHINA = 'Asia/Shanghai'

// “2026-11-21 到期” 用北京时间的日期。
export function chinaDate(iso) {
  if (!iso) return ''
  const day = new Date(iso)
  if (Number.isNaN(day.getTime())) return ''
  return new Intl.DateTimeFormat('sv-SE', { timeZone: CHINA, year: 'numeric', month: '2-digit', day: '2-digit' }).format(day)
}

export function chinaTime(iso) {
  if (!iso) return ''
  const moment = new Date(iso)
  if (Number.isNaN(moment.getTime())) return ''
  return new Intl.DateTimeFormat('sv-SE', { timeZone: CHINA, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
    .format(moment)
}

// 还有几天到期：今天到期写“今天到期”，不到 7 天的提醒一下。
export function expiryText(iso, now = new Date()) {
  const ends = new Date(iso)
  if (Number.isNaN(ends.getTime())) return ''
  const days = Math.ceil((ends.getTime() - now.getTime()) / 86400000)
  if (days <= 1) return `${chinaDate(iso)} 到期（今天）`
  return `${chinaDate(iso)} 到期（还有 ${days} 天）`
}

export function expiresSoon(iso, now = new Date(), days = 7) {
  const ends = new Date(iso)
  return !Number.isNaN(ends.getTime()) && ends.getTime() - now.getTime() < days * 86400000
}

// 明细：“+100 注册赠送 · 欢迎使用镜思 Prismind”、“-3 使用 · AI 解读”。
export function signed(delta) {
  return delta > 0 ? `+${delta}` : `${delta}`
}

export function ledgerText(row) {
  const what = row.kind === 'spend' ? row.feature || row.label : row.label
  return row.note ? `${what} · ${row.note}` : what
}

// 价格表的一行：“每天免费 3 次（今天还剩 2 次），之后每次 3 积分”。
export function priceText(price, unlimited = false) {
  if (unlimited) return '管理员不限次数，不扣积分'
  const today = price.free_per_day ? `每天免费 ${price.free_per_day} 次（今天还剩 ${price.free_left} 次），之后` : ''
  return `${today}每次 ${price.cost} 积分`
}

// 每日打卡：没打的时候写今天能领多少，打过以后写连续了几天、明天能领多少。
export function checkinText(state) {
  if (!state?.enabled) return ''
  if (state.done_today) return `已连续 ${state.streak} 天，明天打卡可得 ${state.next_points} 积分`
  const streak = state.streak ? `已连续 ${state.streak} 天，` : ''
  return `${streak}今天打卡可得 ${state.today_points} 积分`
}

// 连续打卡的 7 格：第几天、送多少、打过没有。连续超过 7 天以后都按第 7 格送，7 格都打勾。
export function checkinCells(state) {
  if (!state?.ladder) return []
  const position = state.done_today ? state.streak : state.streak + 1     // 今天是连续第几天
  const shown = Math.min(position, state.ladder.length)
  return state.ladder.map((points, index) => {
    const day = index + 1
    const status = day < shown || (day === shown && state.done_today) ? 'done' : day === shown ? 'today' : 'later'
    const last = day === state.ladder.length
    return { day, points, status, label: last ? `第 ${day} 天起` : `第 ${day} 天`, short: last ? `${day} 天+` : `${day} 天` }
  })
}

// “10 月 20 日”
export function monthDay(iso) {
  const [, month, day] = String(iso || '').split('-').map(Number)
  return month && day ? `${month} 月 ${day} 日` : ''
}

// 补签卡：有几张、再打几天送一张。
export function cardText(state) {
  if (!state?.card_every) return ''
  return `补签卡 ${state.cards} 张 · 再打卡 ${state.card_in} 天送 1 张`
}

// 用户输入的兑换码：去掉空格、换成大写；格式明显不对时先在页面上提示。
export function cleanCode(text) {
  return String(text || '').replace(/\s+/g, '').toUpperCase()
}

export function codeProblem(text) {
  const code = cleanCode(text)
  if (!code) return '请输入兑换码'
  if (!/^[A-Z0-9-]{6,40}$/.test(code)) return '兑换码只包含字母、数字和短横线'
  return ''
}
