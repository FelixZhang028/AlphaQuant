// AI 研究员页面的展示规则：数据按组排列、倾向的颜色、模型与次数的说明。

export const pointSections = [
  { key: 'bull_points', label: '支持的因素' },
  { key: 'risk_points', label: '风险' },
  { key: 'watch_points', label: '接下来留意' },
]

// 数据按出现顺序分组；后端已经按“基本信息、价格走势……”排好。
export function factGroups(facts = []) {
  const groups = []
  for (const fact of facts) {
    let group = groups.find((item) => item.group === fact.group)
    if (!group) groups.push((group = { group: fact.group, items: [] }))
    group.items.push(fact)
  }
  return groups
}

// 倾向只是对现在数据的归纳：利好因素多、差不多、还是风险因素多，不预测以后的价格。
// 以前保存的记录写的是 偏多/中性/偏空，显示时换成现在的说法；也不用红绿色，免得看起来像买卖信号。
const OLD_TILTS = { 偏多: '利好较多', 中性: '大致相当', 偏空: '风险较多' }
export const TILTS = ['利好较多', '大致相当', '风险较多']
const TILT_LABELS = { ...OLD_TILTS, ...Object.fromEntries(TILTS.map((tilt) => [tilt, tilt])) }
export function normalizeTilt(tilt) {
  return OLD_TILTS[tilt] || tilt || ''
}
export const TILT_NOTE = '对当前数据的归纳，不是买卖建议'
export function tiltLabel(tilt) {
  return TILT_LABELS[tilt] || tilt || ''
}
export function tiltTone(tilt) {
  return TILT_LABELS[tilt] ? 'border-indigo-300/30 bg-indigo-500/10 text-indigo-100' : 'border-white/15 bg-white/5 text-slate-200'
}

// 今天的免费次数；用完以后说明再用一次要多少积分、现在有多少。
export function remainingText(usage, word) {
  if (!usage || usage.remaining == null) return ''
  if (usage.remaining > 0) return `今天还可以免费${word} ${usage.remaining} 次`
  if (usage.cost && usage.points != null) return `今天的免费${word}次数已用完，再用每次 ${usage.cost} 积分（现有 ${usage.points}）`
  return `今天的免费${word}次数已用完`
}

// 还能不能再用一次：今天还有免费次数，或者积分够；管理员（没有次数限制）总是可以。
export function canUse(usage) {
  if (!usage || usage.remaining == null || usage.remaining > 0) return true
  return usage.points != null && Number(usage.points) >= Number(usage.cost || 0)
}

// 按钮上的字：有免费次数时照原样；免费次数用完时写这次要多少积分，积分不够时说清楚差多少。
export function useLabel(usage, label) {
  if (!usage || usage.remaining == null || usage.remaining > 0) return label
  if (canUse(usage)) return `${label} · ${usage.cost} 积分`
  return `积分不够（需要 ${usage.cost}，现有 ${usage.points ?? 0}）`
}

export function modelText(status) {
  if (!status) return '正在读取 AI 模型状态…'
  if (!status.ai?.available) return status.decision?.available
    ? '已配置 Jev 决策模型：可判断数据中的倾向；文字解读和追问需要另外配置文本模型。'
    : '平台还没有配置 AI 模型：分析时只显示数据，不会有 AI 解读。'
  const left = remainingText(status.usage?.brief, '分析')
  return `AI 模型 ${status.ai.model}${left ? ` · ${left}` : ''}`
}

// 依据：只在日期和分析日不同时写日期（例如财报的公告日）。
export function evidenceText(fact, tradeDate) {
  const day = fact.as_of && fact.as_of !== tradeDate ? `（${fact.as_of}）` : ''
  return `${fact.label}：${fact.text}${day}`
}

export function signedPercent(value) {
  return `${value > 0 ? '+' : ''}${(value * 100).toFixed(1)}%`
}

// 分析日之后的实际走势，和同期沪深300比较。
export function laterText(later) {
  if (!later) return ''
  const index = later.benchmark_change == null ? '' : `，同期${later.benchmark} ${signedPercent(later.benchmark_change)}`
  return `分析日之后到 ${later.end_date}（${later.days} 个交易日）：这只股票 ${signedPercent(later.change)}${index}。`
}

// 开始分析时用哪只股票：选过的那只；完整的代码；否则是列表里的第一只。
export function pickSuggestion(text, picked, suggestions = []) {
  if (picked) return picked.symbol
  const typed = String(text || '').trim()
  if (/^\d{6}(\.(SH|SZ|BJ))?$/i.test(typed)) return typed
  const exact = suggestions.find((item) => item.name === typed)
  return (exact || suggestions[0])?.symbol || ''
}

export function percent(value) {
  return `${Math.round(Number(value) * 100)}%`
}

// 决策模型和 AI 解读对同一张数据表的归纳不同时，说明信号不一致。
export function oddsDisagree(odds, tilt) {
  return Boolean(odds && tilt && normalizeTilt(odds.choice) !== normalizeTilt(tilt))
}

export function overfitText(probability) {
  if (probability >= 0.6) return '模型认为这个结果很可能经不起新数据的检验。'
  if (probability >= 0.4) return '模型拿不准，建议用参数验证检查。'
  return '模型认为这个结果不太像是巧合，但仍建议用参数验证确认。'
}
