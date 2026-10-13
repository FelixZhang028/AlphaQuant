// Alpha101 公式因子数量多、名字相近，默认不列出；打开开关后在因子库、评估和组合里都能选。
export const isAlpha101 = (factor) => factor?.source === 'Alpha101'

export function alpha101Count(factors) {
  return factors.filter(isAlpha101).length
}

// 常用因子排在前面，Alpha101 排在后面。关着开关时只列出常用因子；
// 已经被选中的 Alpha101 因子仍然列出，避免“选了却看不见”。
export function visibleFactors(factors, showAlpha101, selectedNames = []) {
  const selected = new Set(selectedNames)
  const alpha = factors.filter((factor) => isAlpha101(factor) && (showAlpha101 || selected.has(factor.name)))
  return [...factors.filter((factor) => !isAlpha101(factor)), ...alpha]
}
