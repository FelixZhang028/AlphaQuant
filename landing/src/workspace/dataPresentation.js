// 概览只描述已保存的数据，不把历史覆盖率当成“已更新到最新交易日”。
export function summarizeDataOverview(overview, { loading = false, error = '' } = {}) {
  const count = (value) => Number.isFinite(Number(value)) && Number(value) >= 0 && value != null && value !== '' ? Number(value) : null
  const symbols = Array.isArray(overview?.per_symbol) ? overview.per_symbol : []
  const total = count(overview?.configured_symbol_count)
  const covered = symbols.filter((row) => Number(row.rows) > 0).length
  const coverage = count(overview?.coverage_ratio)
  const unknown = count(overview?.unknown_status_rows)
  const dates = symbols.filter((row) => Number(row.rows) > 0)
    .map((row) => row.end_date).filter((date) => /^\d{4}-\d{2}-\d{2}$/.test(date || '')).sort()
  const missing = total == null ? null : Math.max(0, total - covered)
  const base = { total, covered, missing, unknown, coverage, through: dates[0] || null }
  const result = (state, title, hint) => ({ ...base, state, title, hint })
  if (error) return result('error', '暂时无法读取数据状态', '请重试；读取失败不代表数据不存在。')
  if (loading || !overview) return result('loading', '正在检查本地数据', '正在读取股票池覆盖情况，请稍候。')
  if (total === 0) return result('empty', '先选好要研究的股票', '添加股票后，再更新行情。')
  if (total == null || coverage == null || coverage > 1 || unknown == null || !Array.isArray(overview.per_symbol)) {
    return result('unknown', '数据状态需要核对', '概览信息不完整，请刷新后查看明细。')
  }
  if (covered === 0) return result('missing', '股票池还没有本地行情', '更新数据后即可查看覆盖情况。')
  if (missing > 0 || coverage < 1) return result('incomplete', '股票池行情还需补齐', '部分股票缺少行情或交易日记录，请更新后核对明细。')
  if (unknown > 0) return result('warning', '有交易状态需要核对', '未知交易状态可能影响回测，请先查看数据详情。')
  return result('covered', '已保存区间的行情覆盖完整', '可以开始研究；回测日期需落在已有行情区间内，不代表行情已更新到最新交易日。')
}

// 估值与换手率的覆盖情况，一句话。status 来自闭环状态接口的 indicators。
export function indicatorSummary(status) {
  if (!status) return ''
  const number = (value) => Number(value || 0).toLocaleString('zh-CN')
  if (!status.symbols) return `还没有下载。本地有行情的 ${number(status.missing_symbols)} 只股票都可以补全。`
  const span = `${status.start_date} 至 ${status.end_date}`
  if (!status.missing_symbols) return `本地有行情的 ${number(status.symbols)} 只股票都已覆盖（${span}）。`
  return `已有 ${number(status.symbols)} 只股票（${span}），还有 ${number(status.missing_symbols)} 只没有。`
}

// 财务数据的覆盖情况，一句话。status 来自闭环状态接口的 fundamentals。
export function fundamentalsSummary(status) {
  if (!status) return ''
  const number = (value) => Number(value || 0).toLocaleString('zh-CN')
  if (!status.symbols) return '还没有下载。'
  const latest = `最新报告期 ${status.latest_stat_date}`
  if (!status.missing_symbols) return `本地有行情的 ${number(status.symbols)} 只股票都有财报（${latest}）。`
  return `已有 ${number(status.symbols)} 只股票的财报（${latest}）；本地有行情的股票里还有 ${number(status.missing_symbols)} 只没有。`
}

// 行业分类的覆盖情况，一句话。status 来自闭环状态接口的 industry。
export function industrySummary(status) {
  if (!status) return ''
  const number = (value) => Number(value || 0).toLocaleString('zh-CN')
  if (!status.snapshots) return '还没有下载。'
  const span = `${status.start_date} 至 ${status.end_date}`
  const missing = status.missing_symbols ? `；有 ${number(status.missing_symbols)} 只没有分类（多数是已经退市的）` : ''
  return `已有 ${number(status.symbols)} 只股票的行业分类（${span}，${number(status.snapshots)} 个时点）${missing}。`
}

// 行情不完整的股票，一句话；没有时返回空串（页面不显示这一栏）。status 来自闭环状态接口的 bar_gaps。
export function barGapSummary(status) {
  if (!status?.symbols) return ''
  const number = (value) => Number(value || 0).toLocaleString('zh-CN')
  const late = (status.examples || []).find((item) => item.first_bar)
  const example = late ? `例如${late.name || late.symbol}（${late.symbol}）应该从 ${late.expected_start} 开始，本地从 ${late.first_bar} 才开始。` : ''
  const absent = status.without_bars ? `其中 ${number(status.without_bars)} 只完全没有行情。` : ''
  return `有 ${number(status.symbols)} 只股票的行情不完整：开始得比上市日期晚，或者完全没有。${example}${absent}`
}

// 指数历史成分股的覆盖情况，每个指数一句话。status 来自闭环状态接口的 index_constituents。
export function indexConstituentsSummary(status) {
  return (status || []).map((item) => {
    if (!item.start_date) return `${item.name}：还没有下载。`
    return `${item.name}：${item.start_date} 至 ${item.end_date}，名单变化过 ${item.changes} 次，现在 ${item.members} 只。`
  })
}

// 因子评估时可以选的中性化方式。
export const NEUTRALIZATION_OPTIONS = [
  { value: 'none', label: '不做', hint: '' },
  { value: 'industry', label: '行业', hint: '去掉行业之间的差别，只比较同行业里的股票。需要先下载行业分类。' },
  { value: 'size', label: '市值', hint: '去掉大小盘的影响。需要先下载财务数据（用到总股本）。' },
  { value: 'both', label: '行业和市值', hint: '同时去掉行业和大小盘的影响。需要先下载行业分类和财务数据。' },
]
