// 研究默认值在页面上的用法。

export const REBALANCE_OPTIONS = [
  { value: 'daily', label: '每日' },
  { value: 'weekly', label: '每周' },
  { value: 'monthly', label: '每月' },
]
export const PERIOD_OPTIONS = [1, 2, 3, 5, 10].map((years) => ({ value: years, label: `最近 ${years} 年` }))

const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

// 默认回测区间：截止到今天，往前 years 年（后端会按本地实际有的行情再收窄）。2 月 29 日往前推到没有闰日的年份时用 2 月 28 日。
export function periodFor(years, today = new Date()) {
  const end = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const start = new Date(end.getFullYear() - years, end.getMonth(), end.getDate())
  if (start.getMonth() !== end.getMonth()) start.setDate(0)
  return { from_date: iso(start), to_date: iso(end) }
}

// 回测表单用默认值：初始资金、最多持仓、调仓频率和区间。
export function backtestDefaults(preferences, today = new Date()) {
  return {
    initial_capital: preferences.initial_capital,
    max_positions: preferences.max_positions,
    rebalance: preferences.rebalance,
    ...periodFor(preferences.period_years, today),
  }
}
