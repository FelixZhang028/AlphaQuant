// 每天自动更新：状态文字（数据更新到哪天、上次更新做了什么、正在做哪一步）。

const STAGES = {
  market_open: '检查今天是否交易',
  security_master: '更新股票列表',
  daily_bars: '下载日线行情',
  corporate_actions: '补分红送转记录',
  benchmarks: '更新指数行情',
  index_constituents: '核对指数成分股',
  industry: '更新行业分类',
  derived: '整理历史股票池',
}

const number = (value) => Number(value || 0).toLocaleString('zh-CN')

export function coverageText(data) {
  if (!data?.latest_date) return '本地还没有行情数据'
  const text = `数据更新到 ${data.latest_date}，这一天有 ${number(data.stocks_on_latest)} 只股票的行情`
  if (!data.listed) return text
  // 不到在市股票的八成：多半是这一天只更新了一部分股票。
  const partial = data.stocks_on_latest < data.listed * 0.8
  return `${text}（在市 ${number(data.listed)} 只）${partial ? '；这一天的行情还不完整' : ''}`
}

export function lastText(last) {
  if (!last) return '还没有运行过每日更新'
  let outcome = { SUCCESS: '完成', PARTIAL: '部分完成', FAILED: '失败', INTERRUPTED: '意外中断', STOPPED: '已停止' }[last.status] || last.status
  if (last.status === 'SUCCESS' && last.market === 'closed') outcome = '不是交易日，没有更新'
  if (last.status === 'SUCCESS' && last.market === 'not_ready') outcome = '当时行情还没有发布'
  const who = last.trigger === 'admin' ? '（管理员手动运行）' : ''
  return `上次更新：${last.trade_date} ${outcome}${who}${last.summary ? `，${last.summary}` : ''}`
}

export function progressText(progress) {
  if (!progress?.stage) return '正在准备'
  const label = STAGES[progress.stage] || progress.stage
  return progress.total > 1 ? `${label} ${number(progress.done)} / ${number(progress.total)}` : label
}
