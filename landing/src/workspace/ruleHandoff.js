// 条件选股和新建规则策略之间带上同一组条件：一边存进 sessionStorage，另一边打开时取走。
// 只是页面之间的交接，读不到（例如浏览器禁用了存储）就当作没有。
const KEY = 'fq-rule-handoff'

export function handOffRules(definition) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(definition))
  } catch {
    /* 没有交接也能用，只是要重新填条件 */
  }
}

export function takeHandedRules() {
  try {
    const text = sessionStorage.getItem(KEY)
    sessionStorage.removeItem(KEY)
    return text ? JSON.parse(text) : null
  } catch {
    return null
  }
}
