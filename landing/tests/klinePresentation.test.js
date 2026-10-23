import assert from 'node:assert/strict'
import test from 'node:test'
import { aggregateBars, barsInRange, formatVolume, isIndexSymbol, klineCaption, quoteSummary, toCandles, tradeMarks } from '../src/workspace/klinePresentation.js'

const bar = (date) => ({ date, open: 10, high: 11, low: 9, close: 10.5, volume: 100 })

test('K线时间取本地零点，显示日期不偏移', () => {
  const [candle] = toCandles([bar('2026-01-05')])
  const day = new Date(candle.timestamp)
  assert.deepEqual([day.getFullYear(), day.getMonth(), day.getDate(), day.getHours()], [2026, 0, 5, 0])
  assert.deepEqual({ ...candle, timestamp: 0 }, { timestamp: 0, open: 10, high: 11, low: 9, close: 10.5, volume: 100 })
})

test('时间范围以最后一根K线为终点，而不是今天', () => {
  const bars = ['2024-03-29', '2025-03-31', '2025-04-01', '2025-12-31', '2026-01-02', '2026-03-31'].map(bar)
  assert.equal(barsInRange(bars, '3m'), 2)
  assert.equal(barsInRange(bars, '1y'), 4)
  assert.equal(barsInRange(bars, '3y'), 6)
  assert.equal(barsInRange(bars, 'all'), 6)
  assert.equal(barsInRange([], '1y'), 0)
})

test('周线和月线由日线合并，跨年的一周不被拆开', () => {
  const day = (date, open, high, low, close, volume) => ({ date, open, high, low, close, volume })
  const bars = [
    day('2025-12-29', 10, 11, 9, 10.5, 100), day('2025-12-31', 10.5, 12, 10, 11, 200),
    day('2026-01-02', 11, 11.5, 8, 9, 300), day('2026-01-05', 9, 9.5, 8.5, 9.2, 400),
  ]
  assert.deepEqual(aggregateBars(bars, 'week'), [
    day('2026-01-02', 10, 12, 8, 9, 600), day('2026-01-05', 9, 9.5, 8.5, 9.2, 400),
  ])
  assert.deepEqual(aggregateBars(bars, 'month'), [
    day('2025-12-31', 10, 12, 9, 11, 300), day('2026-01-05', 11, 11.5, 8, 9.2, 700),
  ])
  assert.equal(aggregateBars(bars, 'day'), bars)
  assert.equal(bars[0].close, 10.5)
})

test('行情摘要按交易日计算涨跌，历史不足的区间不给数字', () => {
  const bars = Array.from({ length: 21 }, (_, index) => ({ ...bar('2026-01-01'), close: 10 + index }))
  const summary = quoteSummary(bars)
  assert.equal(summary.close, 30)
  assert.equal(summary.change, 1)
  assert.equal(summary.changePct, 30 / 29 - 1)
  assert.equal(summary.pct20, 2)
  assert.equal(summary.pct60, null)
  assert.equal(quoteSummary([]), null)
  assert.equal(quoteSummary([bar('2026-01-05')]).change, null)
})

test('回测成交换算到复权价格，并对齐到所在的周K线', () => {
  const day = (date, low, high, factor) => ({ date, open: low, high, low, close: high, volume: 1, factor })
  const bars = [day('2026-01-05', 5, 6, 0.5), day('2026-01-06', 5, 7, 0.5), day('2026-01-12', 10, 12, 1)]
  const trades = {
    fills: [{ date: '2026-01-05', side: 'BUY', price: 11 }, { date: '2026-01-12', side: 'SELL', price: 11.5 },
      { date: '2026-01-08', side: 'BUY', price: 9 }],
    rejected: [{ date: '2026-01-06', side: 'SELL' }],
    holdings: [{ start_date: '2026-01-05', end_date: '2026-01-09' }, { start_date: '2026-02-01', end_date: '2026-02-02' }],
  }
  const daily = tradeMarks(bars, bars, trades)
  assert.deepEqual(daily.marks, [
    { kind: 'buy', buy: true, date: '2026-01-05', value: 5.5, anchor: 5 },
    { kind: 'sell', buy: false, date: '2026-01-12', value: 11.5, anchor: 12 },
    { kind: 'reject', buy: false, date: '2026-01-06', value: null, anchor: 7 },
  ])
  // 01-08 没有日线（例如停牌），这笔成交不画出来，但要计数。
  assert.equal(daily.missing, 1)
  // 持仓到 01-09，图上没有这一天，区间画到之后的第一根 K 线；数据范围之外的持仓不画。
  assert.deepEqual(daily.spans, [{ start: '2026-01-05', end: '2026-01-12' }])

  const weekly = tradeMarks(bars, aggregateBars(bars, 'week'), trades)
  assert.deepEqual(weekly.marks[0], { kind: 'buy', buy: true, date: '2026-01-06', value: 5.5, anchor: 5 })
  assert.equal(weekly.marks[2].date, '2026-01-06')
})

test('成交量按万、亿显示', () => {
  assert.equal(formatVolume(148168594), '1.48亿')
  assert.equal(formatVolume('69097909'), '6909.79万')
  assert.equal(formatVolume(60000000), '6000万')
  assert.equal(formatVolume(8532), '8532')
  assert.equal(formatVolume('n/a'), 'n/a')
})

test('带后缀的是指数，6 位数字是股票：000001.SH 不是平安银行', () => {
  assert.equal(isIndexSymbol('000001.SH'), true)
  assert.equal(isIndexSymbol('399006.sz'), true)
  assert.equal(isIndexSymbol('932000.CSI'), true)
  assert.equal(isIndexSymbol('000001'), false)
  assert.equal(isIndexSymbol(''), false)
  assert.equal(isIndexSymbol(undefined), false)
})

test('K线说明：指数不说复权，股票缺少复权因子时提醒', () => {
  const bars = [bar('2026-01-05'), bar('2026-01-06')]
  const range = { start_date: '2026-01-05', end_date: '2026-01-06', bars }
  assert.equal(klineCaption({ ...range, kind: 'index', adjust: 'none', suspended_days: 0, invalid_rows: 1 }, 'forward'),
    '指数 · 2026-01-05 至 2026-01-06 · 共 2 个交易日 · 成交量单位：股；1 条记录价格不完整未显示')
  assert.equal(klineCaption({ ...range, kind: 'stock', adjust: 'none', suspended_days: 3, invalid_rows: 0 }, 'forward'),
    '不复权 · 2026-01-05 至 2026-01-06 · 共 2 个交易日 · 成交量单位：股；该股票缺少复权因子，当前显示不复权价格；停牌 3 天未显示')
  assert.equal(klineCaption({ ...range, kind: 'stock', adjust: 'forward' }, 'forward'),
    '前复权 · 2026-01-05 至 2026-01-06 · 共 2 个交易日 · 成交量单位：股')
  assert.equal(klineCaption({ ...range, bars: [] }, 'forward'), '')
  assert.equal(klineCaption(null, 'forward'), '')
})
