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
  if (!item.available) return `平台还没有${item.label}的名单，管理员更新后就能用。`
  return `每个调仓日只在当时的成分股里选股，不使用今天的名单。成分股历史从 ${item.start_date} 开始，核对到 ${item.end_date}；开始日期不能早于 ${item.start_date}。`
}

// 因子研究选中某个范围时的说明。股票池只有几只股票时，截面排名和分组说明不了什么。
export function factorUniverseNote(value, markets) {
  const item = (markets || []).find((entry) => entry.value === value)
  if (!item) return ''
  if (item.value === CURRENT_POOL) return '只用股票池里的股票。股票很少时，每天的排名和分组都很粗，IC 说明不了多少问题，建议选择指数。'
  if (!item.available) return `平台还没有${item.label}的名单，管理员更新后就能用。`
  return `每天只用那天在指数里的股票，不用今天的名单；Alpha101 的截面排名也只在当天的成分股之间进行。成分股历史从 ${item.start_date} 开始，开始日期不能早于这一天。`
}

// 因子研究默认的范围：用过的那个；没有用过时，有沪深300 就用沪深300，否则用股票池。
export function defaultFactorUniverse(markets, remembered) {
  const usable = (value) => (markets || []).some((item) => item.value === value && item.available)
  if (remembered && usable(remembered)) return remembered
  return usable('000300.SH') ? '000300.SH' : CURRENT_POOL
}

// 带入以前的回测配置时用：那次的范围现在还能选才带入。
export function usableMarket(value, markets) {
  return (markets || []).some((item) => item.value === value && item.available) ? value : CURRENT_POOL
}
