// 参数优化与样本外验证共用的候选参数整理。

// "10, 20，30" -> [10, 20, 30]；不是数字的保留原文（布尔值、选项名），重复的值只留一个。
export function parseCandidates(raw) {
  const values = String(raw ?? '')
    .split(/[,，]/)
    .map((text) => text.trim())
    .filter(Boolean)
    .map((text) => (Number.isNaN(Number(text)) ? text : Number(text)))
  return [...new Set(values)]
}

// 每行是一个参数及其候选值；没选参数或没填候选值的行不参与。
export function candidateGrid(slots) {
  const grid = {}
  for (const slot of slots) {
    const values = parseCandidates(slot.values)
    if (slot.name && values.length) grid[slot.name] = values
  }
  return grid
}

export function combinationCount(grid) {
  const sizes = Object.values(grid).map((values) => values.length)
  return sizes.length ? sizes.reduce((total, size) => total * size, 1) : 0
}

export function parameterHint(parameter) {
  if (!parameter) return ''
  const parts = [`基准中的取值 ${parameter.current}`]
  if (parameter.choices?.length) parts.push(`可选 ${parameter.choices.join(' / ')}`)
  else if (parameter.kind === 'boolean') parts.push('可填 true / false')
  else if (parameter.minimum != null || parameter.maximum != null) {
    parts.push(`允许范围 ${parameter.minimum ?? '不限'} ~ ${parameter.maximum ?? '不限'}`)
  }
  return parts.join('，')
}
