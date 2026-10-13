// 因子分成两组：常用因子，和折叠起来的 Alpha101 公式因子。
// Alpha101 主要用来学习量价因子是怎么构造的，数量多、名字相近，所以默认折叠。
export const isAlpha101 = (factor) => factor?.source === 'Alpha101'

const ALPHA101_GROUP = {
  key: 'alpha101',
  title: 'Alpha101 公式因子 · 学习用',
  note: '来自公开的《101 Formulaic Alphas》公式集，适合用来学习量价因子是怎么构造的。公式为美股设计，用到策略里之前请先做因子评估。',
  folded: true,
}

// 没有 Alpha101 因子时只有常用这一组；常用组即使为空也保留，页面才能显示“暂无因子”。
export function factorGroups(factors) {
  const groups = [{ key: 'common', title: '常用因子', note: '', folded: false, factors: factors.filter((factor) => !isAlpha101(factor)) }]
  const alpha = factors.filter(isAlpha101)
  if (alpha.length) groups.push({ ...ALPHA101_GROUP, factors: alpha })
  return groups
}

// 这一组里已经选中了几个：折叠着的时候在标题上提示。
export function selectedInGroup(group, selectedNames) {
  const selected = new Set(selectedNames)
  return group.factors.filter((factor) => selected.has(factor.name)).length
}
