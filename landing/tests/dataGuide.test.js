import test from 'node:test'
import assert from 'node:assert/strict'
import { BACKTEST_RULES, LIMITS, NOT_READY, guideRows, headline } from '../src/workspace/dataGuide.js'

const loop = {
  bars_symbols: 5479, bars_min: '2015-01-05', bars_max: '2026-10-13', corporate_action_rows: 61234,
  membership_symbols: 5911, master_delisted: 337,
  indicators: { symbols: 5300, missing_symbols: 179, start_date: '2015-01-05', end_date: '2026-10-13' },
  fundamentals: { symbols: 0, missing_symbols: 5479, latest_stat_date: null },
  industry: { snapshots: 48, symbols: 5400, start_date: '2015-03-31', end_date: '2026-09-30' },
  index_constituents: [{ name: '沪深300', start_date: '2015-01-05', end_date: '2026-10-13', members: 300 }, { name: '中证500' }],
}
const daily = { enabled: true, time: '18:30', data: { latest_date: '2026-10-13', stocks_on_latest: 5224, listed: 5574 } }

test('顶部一句话：更新到哪天、多少只、从哪年起、多久更新', () => {
  assert.equal(headline(loop, daily), '行情更新到 2026-10-13 · 沪深 A 股 5,574 只在市 · 2015 年起 · 每个交易日 18:30 以后自动更新')
  assert.equal(headline(null, { enabled: false, data: {} }), '平台还没有行情数据 · 由管理员定期更新')
})

test('数据清单：每类一行，还没有的写明由平台更新', () => {
  const rows = Object.fromEntries(guideRows(loop, daily).map((row) => [row.key, row]))
  assert.deepEqual(Object.keys(rows), ['bars', 'indicators', 'fundamentals', 'actions', 'industry', 'index_constituents', 'universe'])
  assert.equal(rows.bars.range, '5,479 只股票，2015-01-05 至 2026-10-13')
  assert.equal(rows.bars.now, '更新到 2026-10-13（这一天 5,224 只有行情）')
  assert.equal(rows.indicators.now, '还有 179 只股票没有')
  assert.equal(rows.fundamentals.now, NOT_READY)
  assert.equal(rows.index_constituents.range, '沪深300 2015-01-05 至 2026-10-13')
  assert.equal(rows.universe.range, '5,911 只股票（其中已退市 337 只）')
  assert.ok(guideRows(null, null).every((row) => row.now === NOT_READY))
})

test('说明里不叫用户自己下载，也写清楚当前股票池不含退市股', () => {
  const text = JSON.stringify([BACKTEST_RULES, LIMITS, guideRows(loop, daily)])
  assert.doesNotMatch(text, /请先下载|去下载|数据更新」/)
  assert.ok(LIMITS.some((item) => item.includes('当前股票池') && item.includes('退市')))
})
