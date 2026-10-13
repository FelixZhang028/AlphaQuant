// 因子库的筛选：按来源（内置、Alpha101、自定义……）和类型（动量与趋势、波动与风险……）。
// 筛选项直接来自因子自己的字段，以后增加新的来源或类型时，筛选项会自动出现。
export const ALL = ''

// 常见的值排在前面；没有列在这里的新值按出现的顺序排在后面。
const SOURCE_ORDER = ['内置', 'Alpha101', '自定义']
const TYPE_ORDER = ['动量与趋势', '反转与价格位置', '波动与风险', '成交与流动性', 'K线与量价关系', '基础行情特征']

export const sourceOf = (factor) => factor.source || '其他'
export const typeOf = (factor) => factor.logical_category || factor.category || '未分类'

function ordered(values, preferred) {
  const rank = (value) => (preferred.includes(value) ? preferred.indexOf(value) : preferred.length)
  return [...new Set(values)].map((value, index) => ({ value, index })).sort((a, b) => rank(a.value) - rank(b.value) || a.index - b.index).map((item) => item.value)
}

const matches = (factor, filter) =>
  (!filter.source || sourceOf(factor) === filter.source) && (!filter.type || typeOf(factor) === filter.type)

// 符合筛选条件的因子。keepNames 里的因子（已经选中的）即使不符合条件也保留，避免“选了却看不见”。
export function filterFactors(factors, filter, keepNames = []) {
  const keep = new Set(keepNames)
  return factors.filter((factor) => keep.has(factor.name) || matches(factor, filter))
}

// 两排筛选项。每一项的数量按另一排当前的选择计算，所以看到的数字就是点下去以后的因子数。
export function filterOptions(factors, filter) {
  const row = (valueOf, order, others) => {
    const pool = factors.filter((factor) => matches(factor, others))
    return [
      { value: ALL, label: '全部', count: pool.length },
      ...ordered(factors.map(valueOf), order).map((value) => ({ value, label: value, count: pool.filter((factor) => valueOf(factor) === value).length })),
    ]
  }
  return {
    source: row(sourceOf, SOURCE_ORDER, { source: ALL, type: filter.type }),
    type: row(typeOf, TYPE_ORDER, { source: filter.source, type: ALL }),
  }
}

// 下拉框里按来源分组。
export function factorsBySource(factors) {
  return ordered(factors.map(sourceOf), SOURCE_ORDER).map((source) => ({ label: source, factors: factors.filter((factor) => sourceOf(factor) === source) }))
}
