// 管理后台通用的显示格式。

export const number = (value) => (value == null ? '—' : Number(value).toLocaleString())
export const time = (value) => (value ? new Date(value).toLocaleString() : '—')

export function bytes(value) {
  const n = Number(value)
  if (!Number.isFinite(n) || n < 0) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = n
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  return `${size >= 100 || unit === 0 ? Math.round(size) : size.toFixed(1)} ${units[unit]}`
}

// 本地日期（YYYY-MM-DD），往前 days 天。
export function localDate(days = 0, today = new Date()) {
  const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - days)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
