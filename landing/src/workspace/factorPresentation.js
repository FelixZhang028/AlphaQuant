// 因子库的显示规则：方向、历史长度、一行说明，以及 Alpha101 因子统一的提示。

// Alpha101 的说明末尾都是这一句；表格里不再每行重复，筛选到 Alpha101 时在表格上方提示一次。
export const ALPHA101_SUFFIX = '按原公式计算，正向输出；A股有效性需独立评估。'
export const ALPHA101_NOTE = 'Alpha101 因子来自 WorldQuant 的《101 Formulaic Alphas》，按原公式计算，数值越大越好；在 A 股是否有效需要自己评估，可以先在「因子评估」里看 IC 和分层收益。'

// 方向：因子值越大，预期收益越高（正向）还是越低（反向）。
export function directionText(direction) {
  if (direction === 1) return '↑ 越大越好'
  if (direction === -1) return '↓ 越小越好'
  return '—'
}

export function historyText(days) {
  const value = Number(days)
  return Number.isFinite(value) && value > 0 ? `${value} 天` : '—'
}

// 说明去掉 Alpha101 统一的结尾。
function plainDescription(factor) {
  const text = String(factor?.description || '').trim()
  if (!text.endsWith(ALPHA101_SUFFIX)) return text
  return text.slice(0, -ALPHA101_SUFFIX.length).trim().replace(/[。；;，,]+$/, '')
}

// 表格里的一行说明；说明和名字一样时（Alpha101 就是这样），改为显示公式。
export function factorSummary(factor) {
  const text = plainDescription(factor)
  const name = String(factor?.display_name || factor?.name || '').trim()
  if (!text || text === name) return { text: factor?.formula || '—', formula: Boolean(factor?.formula) }
  return { text, formula: false }
}

// 详情里的“是什么 / 有什么作用”：有专门写的说明就用；Alpha101 和自定义因子各有通用说明。
export function factorNote(factor, notes = {}) {
  if (!factor) return null
  if (notes[factor.name]) return notes[factor.name]
  if (factor.source === 'Alpha101') {
    return { meaning: `${plainDescription(factor) || factor.display_name}。`, usage: ALPHA101_NOTE }
  }
  if (factor.category === '自定义') {
    return {
      meaning: factor.description || '自定义因子：由基础字段与算子组合计算而成。',
      usage: '在「自定义因子」页配置生成，可在因子评估、因子组合与组合研究中与其他因子一样参与合成与验证。',
    }
  }
  return {
    meaning: factor.description || '—',
    usage: '可以在「因子评估」里单独检验，也可以和其他因子一起合成、做组合研究。',
  }
}
