// AI 研究员页面的展示规则：数据按组排列、倾向的颜色、模型与次数的说明。

export const pointSections = [
  { key: 'bull_points', label: '看多的理由' },
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

// A 股习惯红涨绿跌；文字本身写明了倾向，颜色只是辅助。
export function tiltTone(tilt) {
  if (tilt === '偏多') return 'border-rose-400/30 bg-rose-500/10 text-rose-200'
  if (tilt === '偏空') return 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200'
  return 'border-white/15 bg-white/5 text-slate-200'
}

export function remainingText(usage, word) {
  if (!usage || usage.remaining == null) return ''
  return usage.remaining > 0 ? `今天还可以${word} ${usage.remaining} 次` : `今天的${word}次数已用完`
}

export function modelText(status) {
  if (!status) return '正在读取 AI 模型状态…'
  if (!status.ai?.available) return '平台还没有配置 AI 模型：分析时只显示数据，不会有 AI 解读。'
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

// 决策模型对同一张数据表的估计；和 AI 解读的倾向不同时说明信号不一致。
export function oddsText(odds) {
  if (!odds) return ''
  const parts = ['偏多', '中性', '偏空'].map((tilt) => `${tilt} ${percent(odds.probabilities?.[tilt] ?? 0)}`)
  return `决策模型 ${odds.model} 的估计：${parts.join(' · ')}`
}
export function oddsDisagree(odds, tilt) {
  return Boolean(odds && tilt && odds.choice !== tilt)
}

export function overfitText(probability) {
  if (probability >= 0.6) return '模型认为这个结果很可能经不起新数据的检验。'
  if (probability >= 0.4) return '模型拿不准，建议用参数验证检查。'
  return '模型认为这个结果不太像是巧合，但仍建议用参数验证确认。'
}
