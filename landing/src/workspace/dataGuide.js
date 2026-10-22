// “数据说明”页：平台有哪些数据、从哪里来、多久更新一次、回测怎么用、有什么局限。
// 每类数据的“现在”一栏来自闭环状态接口（closedLoopStatus）和每日更新状态（dailyUpdateStatus），只读。

const number = (value) => Number(value || 0).toLocaleString('zh-CN')

// 普通用户看到的“还没有”：数据由平台统一更新，用户不需要也不能自己下载。
export const NOT_READY = '平台还没有这类数据，管理员更新后就能用'

// 页面顶部的一句话总览。
export function headline(loop, daily) {
  const data = daily?.data || {}
  const parts = []
  parts.push(data.latest_date ? `行情更新到 ${data.latest_date}` : '平台还没有行情数据')
  if (data.listed) parts.push(`沪深 A 股 ${number(data.listed)} 只在市`)
  if (loop?.bars_min) parts.push(`${loop.bars_min.slice(0, 4)} 年起`)
  parts.push(daily?.enabled === false ? '由管理员定期更新' : `每个交易日 ${daily?.time || '18:05'} 以后自动更新`)
  return parts.join(' · ')
}

function span(start, end) {
  return start && end ? `${start} 至 ${end}` : ''
}

// 数据清单：每类一行，写清楚内容、范围、多久更新一次、现在的情况。
export function guideRows(loop, daily) {
  const data = daily?.data || {}
  const time = daily?.time || '18:05'
  const everyDay = daily?.enabled === false ? '管理员定期更新' : `每个交易日 ${time} 以后`
  const indicators = loop?.indicators
  const fundamentals = loop?.fundamentals
  const industry = loop?.industry
  const indexes = loop?.index_constituents || []
  const indexReady = indexes.filter((item) => item.start_date)
  return [
    {
      key: 'bars', name: '日线行情',
      content: '每只股票每天的开盘、最高、最低、收盘价，成交量、成交额，以及复权因子',
      range: loop?.bars_symbols ? `${number(loop.bars_symbols)} 只股票，${span(loop.bars_min, loop.bars_max)}` : '—',
      schedule: everyDay,
      now: data.latest_date ? `更新到 ${data.latest_date}（这一天 ${number(data.stocks_on_latest)} 只有行情）` : NOT_READY,
    },
    {
      key: 'indicators', name: '估值与换手率',
      content: '市盈率、市净率、市销率、市现率和换手率，价值类和换手类因子要用到',
      range: indicators?.symbols ? `${number(indicators.symbols)} 只股票，${span(indicators.start_date, indicators.end_date)}` : '—',
      schedule: `和日线一起，${everyDay}`,
      now: indicators?.symbols ? (indicators.missing_symbols ? `还有 ${number(indicators.missing_symbols)} 只股票没有` : '有行情的股票都有') : NOT_READY,
    },
    {
      key: 'fundamentals', name: '财务数据',
      content: '季度财报里的营收、净利润、毛利率、同比增长、资产负债率和总股本；在“股票查询”里打开一只股票就能看到它的历期财报，质量、成长和规模类因子也要用到',
      range: fundamentals?.symbols ? `${number(fundamentals.symbols)} 只股票` : '—',
      schedule: '财报季每周六更新（1～4、7～8、10 月）',
      now: fundamentals?.symbols ? `最新报告期 ${fundamentals.latest_stat_date}` : NOT_READY,
    },
    {
      key: 'actions', name: '分红送转',
      content: '现金分红、送股、转增的记录，回测持有的股票分红送股时按这些记录计入账户',
      range: loop?.corporate_action_rows ? `${number(loop.corporate_action_rows)} 条记录` : '—',
      schedule: everyDay,
      now: loop?.corporate_action_rows ? '随行情一起更新' : NOT_READY,
    },
    {
      key: 'industry', name: '行业分类',
      content: '证监会行业分类，因子评估做行业中性时要用到；每个季度末记一次当时的分类',
      range: industry?.snapshots ? `${number(industry.symbols)} 只股票，${span(industry.start_date, industry.end_date)}` : '—',
      schedule: everyDay,
      now: industry?.snapshots ? `${number(industry.snapshots)} 个时点` : NOT_READY,
    },
    {
      key: 'index_constituents', name: '指数成分股',
      content: '沪深300、上证50、中证500 在历史上每一天的成分股名单，回测时可以选这些指数作为股票范围',
      range: indexReady.length ? indexReady.map((item) => `${item.name} ${span(item.start_date, item.end_date)}`).join('；') : '—',
      schedule: everyDay,
      now: indexReady.length ? indexReady.map((item) => `${item.name}现在 ${item.members} 只`).join('；') : NOT_READY,
    },
    {
      key: 'universe', name: '历史股票池',
      content: '每只股票在哪段时间上市交易，包括后来退市的股票，以及退市时的结算',
      range: loop?.membership_symbols ? `${number(loop.membership_symbols)} 只股票（其中已退市 ${number(loop.master_delisted)} 只）` : '—',
      schedule: everyDay,
      now: loop?.membership_symbols ? '随行情一起更新' : NOT_READY,
    },
  ]
}

// 回测怎么用这些数据：每一条都对照过回测引擎的实际做法，不写做不到的。
export const BACKTEST_RULES = [
  { title: '财报从公布那天起才能用', text: '每份财报记着公布日期。回测和因子评估在某一天只能用到那天以前已经公布的财报，不会提前用到后来才公布的数字。' },
  { title: '指数的成分股按当时的名单', text: '回测选“沪深300 历史成分股”等指数作为股票范围时，每天用那一天的成分股名单，包括后来被调出或退市的股票，而不是用今天的名单回头看。' },
  { title: '退市的股票会结算', text: '持有的股票退市时，按退市时的情况结算，不会把它当作一直持有。' },
  { title: '分红送股计入账户', text: '持有的股票分红、送股、转增时，按记录把现金和新股计入账户。' },
  { title: '按实际交易规则成交', text: '信号出现后在下一个交易日开盘成交；开盘就涨停时买不进，开盘就跌停时卖不出，停牌时不成交；按 100 股一手下单，每只股票一天最多成交当天成交量的 1%，并计算佣金、印花税、过户费和滑点。' },
]

export const LIMITS = [
  '选“当前股票池”作为回测范围时，用的是你自己选的股票，不会自动包含已经退市的股票。想避免只看到“活下来的股票”，可以选指数的历史成分股。',
  '只包含沪深两市的 A 股，不包含北交所、港股和基金。',
  '数据来自公开数据源，偶尔会延迟、出错或缺失；当天的行情要到收盘后才有（数据源大约 17:30 发布，平台 18:05 以后开始更新）。',
  '不包含新闻、公告正文和分析师预测，AI 研究员也只根据这些本地数据分析。',
]

export const SOURCES = '行情、估值、财报、分红、行业和指数成分股主要来自 BaoStock，部分证券信息来自 AkShare 等公开数据源，由平台统一下载和整理。'
