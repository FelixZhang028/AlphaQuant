// 今天符合条件的股票：数值怎么显示、结果怎么概括。后端给的是规则引擎里的指标名。

const PRICE = new Set(['close', 'moving_average', 'previous_high', 'previous_low'])
const SIGNED = new Set(['return', 'drawdown'])

// 一个指标的数值：价格两位小数，涨跌幅和回撤带正负号的百分比，波动率百分比，RSI 一位小数，成交额用万 / 亿。
export function formatIndicator(name, value) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  const number = Number(value)
  if (PRICE.has(name)) return number.toFixed(2)
  if (SIGNED.has(name)) return `${number > 0 ? '+' : ''}${(number * 100).toFixed(2)}%`
  if (name === 'volatility') return `${(number * 100).toFixed(1)}%`
  if (name === 'rsi') return number.toFixed(1)
  if (name === 'average_amount') return number >= 1e8 ? `${(number / 1e8).toFixed(2)} 亿` : `${(number / 1e4).toFixed(0)} 万`
  return number.toFixed(2)
}

// 条件的两边：右边是固定数值时，按左边指标的单位显示（例如“20日涨跌幅大于 0.05”显示成 +5.00%）。
export function conditionValues(result, item, index) {
  const names = result.condition_indicators?.[index] || {}
  const values = item.conditions?.[index] || {}
  return { left: formatIndicator(names.left, values.left), right: formatIndicator(names.right || names.left, values.right) }
}

export function changeText(change) {
  if (change == null || !Number.isFinite(Number(change))) return '—'
  const number = Number(change) * 100
  return `${number > 0 ? '+' : ''}${number.toFixed(2)}%`
}

// “按 2026-10-21 收盘后的数据，在你的股票池 10 只股票里，有 3 只符合条件”
export function screenSummary(result) {
  if (!result) return ''
  const where = result.scope === 'pool' ? '你的股票池' : '全市场'
  const shown = result.shown < result.matched ? `，按排序显示前 ${result.shown} 只` : ''
  return `按 ${result.trade_date} 收盘后的数据，在${where} ${result.checked.toLocaleString('zh-CN')} 只股票里，有 ${result.matched.toLocaleString('zh-CN')} 只符合条件${shown}`
}

// 这组条件过去表现如何：回测结果里的几个数（后端给的已经是百分数，例如 -7.94 表示 -7.94%）。
export function historyMetrics(summary) {
  if (!summary) return []
  const percent = (value, signed = true) => (value == null ? '—' : `${signed && value > 0 ? '+' : ''}${Number(value).toFixed(2)}%`)
  return [
    { label: '区间收益', value: percent(summary.total_return) },
    { label: '年化收益', value: percent(summary.annual_return) },
    { label: '最大回撤', value: summary.max_drawdown == null ? '—' : `-${Math.abs(Number(summary.max_drawdown)).toFixed(2)}%` },
    { label: '夏普比率', value: summary.sharpe == null ? '—' : Number(summary.sharpe).toFixed(2) },
    { label: '完成的交易', value: summary.closed_trades == null ? '—' : `${summary.closed_trades} 笔` },
  ]
}
