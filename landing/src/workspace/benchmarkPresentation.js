// 回测结果和基准（默认沪深 300）的对比：把接口返回的数字整理成页面上的卡片、曲线和说明。
const finite = (value) => value !== null && value !== undefined && Number.isFinite(Number(value))
const signedPercent = (value) => (finite(value) ? `${Number(value) > 0 ? '+' : ''}${Number(value).toFixed(2)}%` : '—')
const tone = (value) => (!finite(value) || Number(value) === 0 ? '' : Number(value) > 0 ? 'text-emerald-300' : 'text-rose-300')

export const STRATEGY_COLOR = '#818cf8'
export const BENCHMARK_COLOR = '#94a3b8'

// 四张卡片：基准自己涨了多少、策略比它多多少、策略跟随基准的程度、去掉跟随部分后剩下的收益。
export function benchmarkCards(benchmark) {
  if (!benchmark?.comparable) return []
  const { name, beta } = benchmark
  return [
    {
      label: `${name} 同期收益`, value: signedPercent(benchmark.benchmark_return), tone: '',
      sub: finite(benchmark.benchmark_max_drawdown) ? `同期最大回撤 ${Number(benchmark.benchmark_max_drawdown).toFixed(2)}%` : '',
    },
    { label: '超额收益', value: signedPercent(benchmark.excess_return), tone: tone(benchmark.excess_return), sub: '策略累计收益减去基准同期收益' },
    {
      label: 'Beta', value: finite(beta) ? Number(beta).toFixed(2) : '—', tone: '',
      sub: finite(beta) ? `基准涨跌 1%，策略平均跟着变动 ${Number(beta).toFixed(2)}%` : '数据太少，无法计算',
    },
    { label: '年化 Alpha', value: signedPercent(benchmark.alpha), tone: tone(benchmark.alpha), sub: '去掉跟随基准的部分后，策略自己的年化收益' },
  ]
}

// 两条累计收益曲线，从同一天的 0% 出发。
export function benchmarkSeries(benchmark) {
  if (!benchmark?.comparable) return []
  const last = (points) => signedPercent(points[points.length - 1])
  return [
    { label: '本策略', color: STRATEGY_COLOR, points: benchmark.strategy_curve, end: last(benchmark.strategy_curve) },
    { label: benchmark.name, color: BENCHMARK_COLOR, points: benchmark.benchmark_curve, end: last(benchmark.benchmark_curve) },
  ]
}

// 卡片下面的一行小字：次要指标和读数时要注意的地方。
export function benchmarkNote(benchmark) {
  if (!benchmark) return ''
  if (!benchmark.comparable) {
    return `${benchmark.name} 的本地行情从 ${benchmark.benchmark_start} 开始，没有覆盖整个回测区间，所以不做比较。`
  }
  const parts = []
  if (finite(benchmark.information_ratio)) parts.push(`信息比率 ${Number(benchmark.information_ratio).toFixed(2)}`)
  if (finite(benchmark.tracking_error)) parts.push(`年化跟踪误差 ${Number(benchmark.tracking_error).toFixed(2)}%`)
  const metrics = parts.length ? `${parts.join(' · ')}。` : ''
  return `${metrics}${benchmark.name} 是价格指数，不含成分股的分红，所以基准收益略微偏低。`
}
