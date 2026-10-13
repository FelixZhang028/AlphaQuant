// 研究记录页与回测结果页共用：记录编号、对比勾选、记录数量的一句话说明。
export const MAX_COMPARED = 5

// 'run-12'、'12'、12 都指第 12 条回测记录；其他写法返回 null。
export function backtestId(reference) {
  const id = Number(String(reference ?? '').replace(/^run-/, ''))
  return Number.isInteger(id) && id > 0 ? id : null
}

// 勾选或取消一条记录；已选满时返回 null，由页面提示。
export function toggleSelection(selected, runId, limit = MAX_COMPARED) {
  if (selected.includes(runId)) return selected.filter((id) => id !== runId)
  return selected.length >= limit ? null : [...selected, runId]
}

// 后端保存的是带时区的时间戳，页面上显示成本地时间，到分钟。
export function runTime(value) {
  const at = new Date(value || '')
  if (Number.isNaN(at.getTime())) return '—'
  const two = (n) => String(n).padStart(2, '0')
  return `${at.getFullYear()}-${two(at.getMonth() + 1)}-${two(at.getDate())} ${two(at.getHours())}:${two(at.getMinutes())}`
}

export function recordsSummary(total, stats) {
  if (!total) return '还没有回测记录。'
  const parts = [`成功 ${stats?.success ?? 0}`, `失败 ${stats?.failed ?? 0}`]
  if (stats?.legacy_unverified) parts.push(`旧版未验证 ${stats.legacy_unverified}`)
  return `共 ${total} 条：${parts.join('，')}。`
}
