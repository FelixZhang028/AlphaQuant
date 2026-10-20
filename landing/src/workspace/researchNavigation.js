// Only these research-context values travel between views and survive refresh/back.
// preset：事件研究预先填好的条件（从 AI研究员 的“这只股票现在的状态”跳过来）。
export const researchQueryKeys = ['strategy', 'run', 'baseline', 'mode', 'symbol', 'brief', 'preset']

export function researchContext(url) {
  return Object.fromEntries(researchQueryKeys.map((key) => [key, url.searchParams.get(key) || '']))
}

export function researchUrl(current, destination) {
  const target = typeof destination === 'string' ? { view: destination } : destination
  const url = new URL(current)
  for (const key of researchQueryKeys) url.searchParams.delete(key)
  url.searchParams.set('view', target.view)
  for (const key of researchQueryKeys) {
    if (target[key] !== undefined && target[key] !== '') url.searchParams.set(key, String(target[key]))
  }
  return url
}

export function openResearch(view, context = {}) {
  window.dispatchEvent(new CustomEvent('fq-navigate', { detail: { view, ...context } }))
}

export function strategyReference(asset) {
  return `package:${asset.package_id}`
}
