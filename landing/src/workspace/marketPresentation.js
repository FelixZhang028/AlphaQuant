// 回测的股票范围：自己的股票池，或者某个指数「当时的成分股」。
// markets 来自回测目录接口的 markets：[{ value, label, available, start_date, end_date }]。

export const CURRENT_POOL = '当前股票池'
const FALLBACK = [{ value: CURRENT_POOL, label: '当前股票池', available: true }]

// 下拉框的选项。还没有下载成分股历史的指数不能选，并写明原因。
export function marketChoices(markets) {
  return (markets?.length ? markets : FALLBACK).map((item) => ({
    value: item.value,
    label: item.available ? item.label : `${item.label}（未下载）`,
    disabled: !item.available,
  }))
}

// 结果页显示的名称；不认识的值原样显示。
export function marketLabel(value, markets) {
  return (markets?.length ? markets : FALLBACK).find((item) => item.value === value)?.label || value || ''
}

// 选中某个范围时，表单下方的一句说明。
export function marketNote(value, markets) {
  const item = (markets || []).find((entry) => entry.value === value)
  if (!item || item.value === CURRENT_POOL) return ''
  if (!item.available) return `还没有下载${item.label}，请先到「数据更新」下载指数成分股。`
  return `每个调仓日只在当时的成分股里选股，不使用今天的名单。成分股历史从 ${item.start_date} 开始，核对到 ${item.end_date}；开始日期不能早于 ${item.start_date}。`
}

// 带入以前的回测配置时用：那次的范围现在还能选才带入。
export function usableMarket(value, markets) {
  return (markets || []).some((item) => item.value === value && item.available) ? value : CURRENT_POOL
}
