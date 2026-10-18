// 规则策略的表单与接口里的 definition 之间的转换。
// 模板、一句话生成、自己填写，最后都落在同一张表单上。
//
// definition（接口）：{ name, entry_logic, entry_rules: [{ left, operator, value | right }], ranking: { indicator, direction } }
// 其中 left / right / indicator 是 { name, window? }；收盘价没有周期。

// windows: { 指标名: { default, minimum, maximum } | null }
function side(name, windows, window) {
  const limits = windows[name]
  return { name, window: limits ? Number(window ?? limits.default) : null }
}

function firstIndicator(options) {
  return Object.keys(options.indicators)[0]
}

export function blankRule(options) {
  const name = firstIndicator(options)
  return {
    left: side(name, options.indicator_windows),
    operator: Object.keys(options.operators)[0],
    compare: 'value',
    value: 0,
    right: side(name, options.indicator_windows),
  }
}

export function blankForm(options) {
  return {
    name: '',
    entry_logic: 'all',
    rules: [blankRule(options)],
    ranking: { ...side(firstIndicator(options), options.indicator_windows), direction: 'descending' },
    top_n: 5,
    rebalance: 'weekly',
  }
}

// 换指标时周期回到该指标的默认值；没有周期的指标清空周期。
export function chooseIndicator(target, name, options) {
  Object.assign(target, side(name, options.indicator_windows))
}

export function formFromDefinition(definition, settings, options) {
  const windows = options.indicator_windows
  const fallback = blankRule(options)
  return {
    name: definition.name || '',
    entry_logic: definition.entry_logic === 'any' ? 'any' : 'all',
    rules: (definition.entry_rules || []).map((rule) => ({
      left: side(rule.left.name, windows, rule.left.window),
      operator: rule.operator,
      compare: rule.right ? 'indicator' : 'value',
      value: rule.right ? 0 : Number(rule.value),
      // 每条规则各有一份，改一条不会影响另一条。
      right: rule.right ? side(rule.right.name, windows, rule.right.window) : { ...fallback.right },
    })),
    ranking: {
      ...side(definition.ranking.indicator.name, windows, definition.ranking.indicator.window),
      direction: definition.ranking.direction === 'ascending' ? 'ascending' : 'descending',
    },
    top_n: Number(settings.top_n),
    rebalance: settings.rebalance,
  }
}

function indicator(item) {
  return item.window == null ? { name: item.name } : { name: item.name, window: Number(item.window) }
}

export function definitionFromForm(form) {
  return {
    name: form.name.trim(),
    entry_logic: form.entry_logic,
    entry_rules: form.rules.map((rule) => ({
      left: indicator(rule.left),
      operator: rule.operator,
      ...(rule.compare === 'indicator' ? { right: indicator(rule.right) } : { value: Number(rule.value) }),
    })),
    ranking: { indicator: indicator(form.ranking), direction: form.ranking.direction },
  }
}

// 保存和检查共用的请求体。origin 记录表单是从哪里开始的，后端据此标注来源。
export function packagePayload(form, origin) {
  const payload = {
    definition: definitionFromForm(form),
    top_n: Number(form.top_n),
    rebalance: form.rebalance,
    source: 'visual_builder',
  }
  if (origin?.kind === 'template') Object.assign(payload, { source: `template:${origin.template_id}`, style: origin.style })
  else if (origin?.kind === 'describe') payload.source = 'nl_builder'
  return payload
}

// 策略列表里的来源小标签。
export function sourceLabel(source) {
  const text = String(source || '')
  if (text.startsWith('template_modified:')) return '基于模板修改'
  if (text.startsWith('template:')) return '模板'
  if (text.startsWith('copy:')) return '副本'
  return { visual_builder: '自己填写', nl_builder: '一句话生成' }[text] || '规则策略'
}
