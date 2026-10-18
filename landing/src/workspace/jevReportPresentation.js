// Display only saved model answers; prose is a fixed explanation of typed results.
export function probabilityLabel(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1
    ? `${(value * 100).toFixed(1).replace(/\.0$/, '')}%` : '—'
}

export function confidenceLabel(value) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > 1) return '未提供'
  return value >= 0.7 ? '较高' : value >= 0.5 ? '一般' : '较低'
}

export function distributionRows(probabilities = {}) {
  return Object.entries(probabilities || {}).map(([label, value]) => ({
    label, text: probabilityLabel(value), width: probabilityLabel(value) === '—' ? '0%' : `${value * 100}%`,
  }))
}

export function reportSummary(report) {
  if (report?.summary) return report.summary
  return {
    偏多: '当前保存的判断偏多，需要结合风险和数据范围理解。',
    中性: '当前保存的判断偏中性，尚未形成明确的方向优势。',
    偏空: '当前保存的判断偏空，需要优先核查不利线索。',
  }[report?.choice] || '暂无综合判断。'
}

export function assessmentTone(value) {
  return {
    支持: 'border-emerald-400/25 bg-emerald-500/10 text-emerald-200',
    需留意: 'border-amber-400/25 bg-amber-500/10 text-amber-200',
    中性: 'border-indigo-400/25 bg-indigo-500/10 text-indigo-200',
  }[value] || 'border-white/10 bg-white/5 text-slate-400'
}

export function isDetailedReport(report) {
  return Number(report?.report_version) >= 2 && Array.isArray(report?.dimensions) && report.dimensions.length > 0
}
